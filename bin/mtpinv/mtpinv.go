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

func cmdInventory(debug bool, storageWant uint32, roots []string, includeHidden bool) {
	if len(roots) == 0 {
		fail("inventory needs at least one root path")
	}
	dev := openDevice(debug)
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
	}{Storage: sid, Roots: roots, Files: []fileEntry{}, Errors: []rootErr{}}

	for _, root := range roots {
		_, _, dirs, err := mtpx.Walk(dev, sid, root, true, false, !includeHidden,
			func(objectId uint32, fi *mtpx.FileInfo, werr error) error {
				if werr != nil {
					return werr
				}
				// The Walk callback fires for the root itself and every descendant.
				// Emit files only; directories are traversed but not listed.
				if fi.IsDir {
					return nil
				}
				out.Files = append(out.Files, fileEntry{
					Path:     fi.FullPath,
					Name:     fi.Name,
					Size:     fi.Size,
					IsDir:    false,
					MTime:    fi.ModTime.UTC().Format(time.RFC3339),
					ObjectID: fi.ObjectId,
				})
				return nil
			})
		if err != nil {
			out.Errors = append(out.Errors, rootErr{Root: root, Error: err.Error()})
			continue
		}
		out.Dirs += dirs
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
	debug := flag.Bool("debug", false, "enable MTP debug logging to stderr")
	storage := flag.Uint("storage", 0, "storage id (0 = first)")
	includeHidden := flag.Bool("all", false, "include hidden files/dirs (dot-prefixed); default skips them")
	flag.Parse()
	args := flag.Args()
	if len(args) == 0 {
		fail("usage: mtpinv [storages|inventory|pull] ...")
	}
	switch args[0] {
	case "storages":
		cmdStorages(*debug)
	case "inventory":
		cmdInventory(*debug, uint32(*storage), args[1:], *includeHidden)
	case "pull":
		if len(args) != 3 {
			fail("usage: mtpinv -storage <id> pull <remotePath> <destDir>")
		}
		cmdPull(*debug, uint32(*storage), args[1], args[2])
	default:
		fail("unknown subcommand %q", args[0])
	}
}
