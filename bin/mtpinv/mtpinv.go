// mtpinv - a small, machine-readable MTP inventory/pull helper built directly on
// github.com/ganeshrvel/go-mtpx (the same library the SwiftMTP CLI bundles). It
// exists because the stock `swiftmtp-cli ls` returns empty listings on some
// devices (a bug in the CLI's stale-generation wrapper, not the library). This
// helper calls go-mtpx Walk/DownloadFiles directly and emits JSON.
//
// Subcommands:
//   mtpinv storages
//       -> {"storages":[{"id":65537,"description":"...","free":N,"max":N}]}
//   mtpinv inventory -storage <id> <root> [<root>...]
//       -> {"storage":65537,"roots":[...],"files":[{path,name,size,mtime,object_id}],
//           "dirs":N,"errors":[{root,error}]}
//   mtpinv pull -storage <id> <remotePath> <destDir>
//       -> {"pulled":"<remotePath>","dest":"<destDir>","bytes":N}
//
// It never writes to the device (only GetObjectHandles / GetObjectInfo / read).
package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"strings"
	"time"

	mtpx "github.com/ganeshrvel/go-mtpx"
	"github.com/ganeshrvel/go-mtpfs/mtp"
)

type fileEntry struct {
	Path     string `json:"path"`
	Name     string `json:"name"`
	Size     int64  `json:"size"`
	IsDir    bool   `json:"is_dir"`
	MTime    string `json:"mtime"`
	ObjectID uint32 `json:"object_id"`
}

func fail(format string, args ...interface{}) {
	fmt.Fprintf(os.Stderr, "mtpinv: "+format+"\n", args...)
	os.Exit(1)
}

func emit(v interface{}) {
	enc := json.NewEncoder(os.Stdout)
	if err := enc.Encode(v); err != nil {
		fail("json encode: %v", err)
	}
}

func openDevice(debug bool) *mtp.Device {
	dev, err := mtpx.Initialize(mtpx.Init{DebugMode: debug})
	if err != nil {
		fail("initialize: %v", err)
	}
	return dev
}

func pickStorage(dev *mtp.Device, want uint32) uint32 {
	storages, err := mtpx.FetchStorages(dev)
	if err != nil {
		fail("fetch storages: %v", err)
	}
	if len(storages) == 0 {
		fail("no storage on device")
	}
	if want == 0 {
		return storages[0].Sid
	}
	for _, s := range storages {
		if s.Sid == want {
			return s.Sid
		}
	}
	fail("storage %d not found", want)
	return 0
}

func cmdStorages(debug bool) {
	dev := openDevice(debug)
	defer mtpx.Dispose(dev)
	storages, err := mtpx.FetchStorages(dev)
	if err != nil {
		fail("fetch storages: %v", err)
	}
	type st struct {
		ID          uint32 `json:"id"`
		Description string `json:"description"`
		Free        uint64 `json:"free"`
		Max         uint64 `json:"max"`
	}
	out := struct {
		Storages []st `json:"storages"`
	}{}
	for _, s := range storages {
		out.Storages = append(out.Storages, st{
			ID:          s.Sid,
			Description: s.Info.StorageDescription,
			Free:        s.Info.FreeSpaceInBytes,
			Max:         s.Info.MaxCapability,
		})
	}
	emit(out)
}

// walkStats records why children were kept or dropped during enumeration. It is
// the evidence for the "GetObjectInfo silently fails per child" hypothesis: if
// info_failed > 0 the stock proccessWalk (which just `continue`s) would have
// silently dropped those files. `recovered` counts children rescued via the
// object-property fallback.
type walkStats struct {
	Handles     int64 `json:"handles"`
	InfoOK      int64 `json:"info_ok"`
	InfoFailed  int64 `json:"info_failed"`
	Recovered   int64 `json:"recovered"`
	Unrecovered int64 `json:"unrecovered"`
}

type propU16 struct{ Value uint16 }

// objectMeta fetches a child's metadata. It tries GetObjectInfo first (the path
// stock go-mtpx uses); if that fails and doRecover is set, it falls back to
// per-property GetObjectPropValue(ObjectFileName/ObjectFormat/ObjectSize/
// DateModified). Returns ok=false only when the object cannot be described at
// all (then it is dropped, exactly as stock behaviour, but now counted/logged).
func objectMeta(dev *mtp.Device, oid uint32, st *walkStats, doRecover, debug bool,
) (name string, size int64, isDir bool, mtime time.Time, ok bool) {
	var obj mtp.ObjectInfo
	if err := dev.GetObjectInfo(oid, &obj); err == nil {
		st.InfoOK++
		isDir = obj.ObjectFormat == mtp.OFC_Association
		name = obj.Filename
		mtime = obj.ModificationDate
		if !isDir {
			if obj.CompressedSize == 0xffffffff { // >4 GiB: real size lives in a prop
				var v mtp.Uint64Value
				if e := dev.GetObjectPropValue(oid, mtp.OPC_ObjectSize, &v); e == nil {
					size = int64(v.Value)
				}
			} else {
				size = int64(obj.CompressedSize)
			}
		}
		return name, size, isDir, mtime, true
	} else {
		st.InfoFailed++
		if debug {
			fmt.Fprintf(os.Stderr, "mtpinv: GetObjectInfo(handle=%d) failed: %v\n", oid, err)
		}
		if !doRecover {
			return "", 0, false, time.Time{}, false
		}
		if n, sz, dir, mt, ok2 := propFallback(dev, oid); ok2 {
			st.Recovered++
			if debug {
				fmt.Fprintf(os.Stderr, "mtpinv: recovered handle=%d name=%q via properties\n", oid, n)
			}
			return n, sz, dir, mt, true
		}
		st.Unrecovered++
		if debug {
			fmt.Fprintf(os.Stderr, "mtpinv: property fallback failed for handle=%d\n", oid)
		}
		return "", 0, false, time.Time{}, false
	}
}

func propFallback(dev *mtp.Device, oid uint32) (name string, size int64, isDir bool, mtime time.Time, ok bool) {
	var fn mtp.StringValue
	if err := dev.GetObjectPropValue(oid, mtp.OPC_ObjectFileName, &fn); err != nil || fn.Value == "" {
		return "", 0, false, time.Time{}, false
	}
	name = fn.Value
	var fmtv propU16
	if err := dev.GetObjectPropValue(oid, mtp.OPC_ObjectFormat, &fmtv); err == nil {
		isDir = fmtv.Value == mtp.OFC_Association
	}
	if !isDir {
		var sz mtp.Uint64Value
		if err := dev.GetObjectPropValue(oid, mtp.OPC_ObjectSize, &sz); err == nil {
			size = int64(sz.Value)
		}
	}
	var dm mtp.StringValue
	if err := dev.GetObjectPropValue(oid, mtp.OPC_DateModified, &dm); err == nil {
		mtime = parseMtpDate(dm.Value)
	}
	return name, size, isDir, mtime, true
}

// parseMtpDate parses the MTP DateModified string ("YYYYMMDDThhmmss[.s][Z]").
// Returns the zero time on failure (callers format it, which is acceptable for a
// recovered file whose GetObjectInfo already failed).
func parseMtpDate(s string) time.Time {
	s = strings.TrimSpace(s)
	if s == "" {
		return time.Time{}
	}
	core := s
	if i := strings.IndexByte(core, '.'); i >= 0 {
		core = core[:i]
	}
	core = strings.TrimSuffix(core, "Z")
	if t, err := time.Parse("20060102T150405", core); err == nil {
		return t
	}
	return time.Time{}
}

// walkDir recursively enumerates a directory by object handle, using objectMeta
// per child. Unlike stock proccessWalk, per-child failures are counted (and
// optionally recovered) rather than invisibly dropped.
func walkDir(dev *mtp.Device, sid, parentId uint32, parentPath string, includeHidden bool,
	st *walkStats, doRecover, debug bool, emitFile func(fileEntry), dirs *int64) error {
	handles := mtp.Uint32Array{}
	if err := dev.GetObjectHandles(sid, mtp.GOH_ALL_ASSOCS, parentId, &handles); err != nil {
		return err
	}
	st.Handles += int64(len(handles.Values))
	for _, oid := range handles.Values {
		name, size, isDir, mtime, ok := objectMeta(dev, oid, st, doRecover, debug)
		if !ok {
			continue
		}
		if !includeHidden && strings.HasPrefix(name, ".") {
			continue
		}
		full := strings.TrimRight(parentPath, "/") + "/" + name
		if isDir {
			*dirs++
			if err := walkDir(dev, sid, oid, full, includeHidden, st, doRecover, debug, emitFile, dirs); err != nil {
				if debug {
					fmt.Fprintf(os.Stderr, "mtpinv: listing %q failed: %v\n", full, err)
				}
			}
		} else {
			emitFile(fileEntry{
				Path:     full,
				Name:     name,
				Size:     size,
				IsDir:    false,
				MTime:    mtime.UTC().Format(time.RFC3339),
				ObjectID: oid,
			})
		}
	}
	return nil
}

func cmdInventory(mtpDebug, debug, doRecover bool, storageWant uint32, roots []string, includeHidden bool) {
	if len(roots) == 0 {
		fail("inventory needs at least one root path")
	}
	dev := openDevice(mtpDebug)
	defer mtpx.Dispose(dev)
	sid := pickStorage(dev, storageWant)

	type rootErr struct {
		Root  string `json:"root"`
		Error string `json:"error"`
	}
	out := struct {
		Storage uint32      `json:"storage"`
		Roots   []string    `json:"roots"`
		Files   []fileEntry `json:"files"`
		Dirs    int64       `json:"dirs"`
		Errors  []rootErr   `json:"errors"`
		Stats   walkStats   `json:"stats"`
	}{Storage: sid, Roots: roots, Files: []fileEntry{}, Errors: []rootErr{}}

	st := &walkStats{}
	emitFile := func(fe fileEntry) { out.Files = append(out.Files, fe) }
	for _, root := range roots {
		fi, err := mtpx.GetObjectFromPath(dev, sid, root)
		if err != nil {
			out.Errors = append(out.Errors, rootErr{Root: root, Error: err.Error()})
			continue
		}
		if !fi.IsDir {
			// A root that is itself a file: emit it directly.
			if !includeHidden && strings.HasPrefix(fi.Name, ".") {
				continue
			}
			emitFile(fileEntry{Path: fi.FullPath, Name: fi.Name, Size: fi.Size,
				MTime: fi.ModTime.UTC().Format(time.RFC3339), ObjectID: fi.ObjectId})
			continue
		}
		if err := walkDir(dev, sid, fi.ObjectId, strings.TrimRight(root, "/"),
			includeHidden, st, doRecover, debug, emitFile, &out.Dirs); err != nil {
			out.Errors = append(out.Errors, rootErr{Root: root, Error: err.Error()})
		}
	}
	out.Stats = *st
	if debug {
		fmt.Fprintf(os.Stderr, "mtpinv: stats handles=%d info_ok=%d info_failed=%d recovered=%d unrecovered=%d\n",
			st.Handles, st.InfoOK, st.InfoFailed, st.Recovered, st.Unrecovered)
	}
	emit(out)
}

func cmdPull(debug bool, storageWant uint32, remote, destDir string) {
	if remote == "" || destDir == "" {
		fail("pull needs <remotePath> and <destDir>")
	}
	if err := os.MkdirAll(destDir, 0o755); err != nil {
		fail("mkdir dest: %v", err)
	}
	dev := openDevice(debug)
	defer mtpx.Dispose(dev)
	sid := pickStorage(dev, storageWant)

	sent, size, err := mtpx.DownloadFiles(dev, sid, []string{remote}, destDir, false, nil,
		func(pi *mtpx.ProgressInfo, perr error) error { return perr })
	if err != nil {
		fail("download %q: %v", remote, err)
	}
	emit(struct {
		Pulled string `json:"pulled"`
		Dest   string `json:"dest"`
		Files  int64  `json:"files"`
		Bytes  int64  `json:"bytes"`
	}{Pulled: remote, Dest: destDir, Files: sent, Bytes: size})
}

func main() {
	mtpDebug := flag.Bool("mtpdebug", false, "enable deep go-mtpx protocol logging to stderr")
	debug := flag.Bool("debug", false, "log per-child GetObjectInfo failures + enumeration stats to stderr")
	doRecover := flag.Bool("recover", false, "on GetObjectInfo failure, fall back to per-property metadata "+
		"(GetObjectPropValue) instead of silently dropping the child")
	storage := flag.Uint("storage", 0, "storage id (0 = first)")
	includeHidden := flag.Bool("all", false, "include hidden files/dirs (dot-prefixed); default skips them")
	flag.Parse()
	args := flag.Args()
	if len(args) == 0 {
		fail("usage: mtpinv [storages|inventory|pull] ...")
	}
	switch args[0] {
	case "storages":
		cmdStorages(*mtpDebug)
	case "inventory":
		cmdInventory(*mtpDebug, *debug, *doRecover, uint32(*storage), args[1:], *includeHidden)
	case "pull":
		if len(args) != 3 {
			fail("usage: mtpinv -storage <id> pull <remotePath> <destDir>")
		}
		cmdPull(*mtpDebug, uint32(*storage), args[1], args[2])
	default:
		fail("unknown subcommand %q", args[0])
	}
}
