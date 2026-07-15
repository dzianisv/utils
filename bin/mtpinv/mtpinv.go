// mtpinv - a small, machine-readable MTP inventory/pull helper built directly on
// github.com/ganeshrvel/go-mtpx (the same library the SwiftMTP CLI bundles). It
// exists because the stock `swiftmtp-cli ls` returns empty listings on some
// devices (a bug in the CLI's stale-generation wrapper, not the library). This
// helper calls go-mtpx Walk/DownloadFiles directly and emits JSON.
//
// Global flags MUST precede the subcommand (Go's stdlib `flag` stops at the
// first non-flag token), e.g. `mtpinv -storage 65537 inventory /DCIM`.
//
// Subcommands:
//
//	mtpinv storages
//	    -> {"storages":[{"id":65537,"description":"...","free":N,"max":N}]}
//	mtpinv -storage <id> inventory <root> [<root>...]
//	    -> {"storage":65537,"roots":[...],"files":[{path,name,size,mtime,object_id}],
//	        "dirs":N,"errors":[{root,error}]}
//	mtpinv -storage <id> pull <remotePath> <destDir>
//	    -> {"pulled":"<remotePath>","dest":"<destDir>","files":N,"bytes":N}
//	mtpinv -storage <id> serve
//	    -> a persistent, single-session request/response loop that reads
//	       newline-delimited JSON requests on stdin and streams newline-delimited
//	       JSON events on stdout. One MTP Initialize/Dispose covers the whole run
//	       (no per-file session churn). See the serve* types below for the wire
//	       protocol. Read-only with respect to the device.
//
// It never writes to the device (only GetObjectHandles / GetObjectInfo / read).
package main

import (
	"bufio"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"time"

	"github.com/ganeshrvel/go-mtpfs/mtp"
	mtpx "github.com/ganeshrvel/go-mtpx"
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

// --- serve: persistent single-session request/response protocol ---------------
//
// Wire protocol (all messages are one JSON object per line / NDJSON):
//
//   stdin  request : {"cmd":"pull","remote":"<abs remote path>","dest":"<abs local file path>"}
//                    {"cmd":"ping"}
//                    {"cmd":"quit"}
//   stdout events  : {"type":"ready","storage":65537,"pid":1234}
//                    {"type":"progress","remote":"...","sent":N,"total":N,"pct":P}
//                    {"type":"complete","remote":"...","dest":"...","bytes":N,"total":N}
//                    {"type":"error","remote":"...","error":"...","fatal":true|false}
//                    {"type":"pong"}
//                    {"type":"bye"}
//
// Semantics:
//   * The device session is opened once (Initialize) before "ready" and disposed
//     once on quit/EOF. Every "pull" reads a single object in that same session,
//     so a whole backup run costs ONE Initialize/Dispose, not N.
//   * "pull" writes the object bytes to the caller-provided absolute `dest` path
//     with os.Create (truncating). NO fsync and NO verification are done here:
//     the Python driver owns the durability/verification transaction (expected
//     size, SHA-256, fsync, atomic publish, manifest commit). The helper only
//     moves bytes.
//   * A path-resolution / not-a-file / local-create failure is reported as a
//     NON-fatal error (the session is still healthy) and serving continues.
//   * A failure DURING the byte stream (dev.GetObject) means the USB/MTP session
//     is compromised; it is reported as a FATAL error and the helper exits so the
//     driver can reopen a fresh session and continue from the manifest.

type serveRequest struct {
	Cmd    string `json:"cmd"`
	Remote string `json:"remote"`
	Dest   string `json:"dest"`
}

type serveEvent struct {
	Type   string `json:"type"`
	Remote string `json:"remote,omitempty"`
	Dest   string `json:"dest,omitempty"`
	Sent   int64  `json:"sent,omitempty"`
	Total  int64  `json:"total,omitempty"`
	// Pct is a pointer so a genuine 0% is still serialized (omitempty on a value
	// would drop it, and the driver computes its own throughput anyway).
	Pct     *float64 `json:"pct,omitempty"`
	Bytes   int64    `json:"bytes,omitempty"`
	Storage uint32   `json:"storage,omitempty"`
	PID     int      `json:"pid,omitempty"`
	Error   string   `json:"error,omitempty"`
	Fatal   bool     `json:"fatal,omitempty"`
}

// serveEmitter serializes events to stdout as NDJSON. os.Stdout writes are
// unbuffered syscalls, so each event reaches the reader promptly. A write error
// (e.g. the driver closed the pipe) is returned so the caller can abort.
type serveEmitter struct{ enc *json.Encoder }

func newServeEmitter() *serveEmitter { return &serveEmitter{enc: json.NewEncoder(os.Stdout)} }

func (e *serveEmitter) send(ev serveEvent) error { return e.enc.Encode(&ev) }

func pct(sent, total int64) float64 {
	if total <= 0 {
		return 0
	}
	return float64(sent) / float64(total) * 100.0
}

// servePull streams one object to dest. Returns (fatal, err) where a non-nil err
// was already emitted; fatal=true means the session is dead and serve must exit.
func servePull(dev *mtp.Device, sid uint32, em *serveEmitter, remote, dest string) (fatal bool, err error) {
	if remote == "" || dest == "" {
		return false, em.send(serveEvent{Type: "error", Remote: remote,
			Error: "pull needs non-empty remote and dest", Fatal: false})
	}

	fi, gerr := mtpx.GetObjectFromPath(dev, sid, remote)
	if gerr != nil {
		// Path resolution failure: the session is still healthy, keep serving.
		return false, em.send(serveEvent{Type: "error", Remote: remote,
			Error: "resolve: " + gerr.Error(), Fatal: false})
	}
	if fi.IsDir {
		return false, em.send(serveEvent{Type: "error", Remote: remote,
			Error: "refusing to pull a directory", Fatal: false})
	}

	f, cerr := os.Create(dest)
	if cerr != nil {
		// Local filesystem problem, not the device's fault: non-fatal.
		return false, em.send(serveEvent{Type: "error", Remote: remote,
			Error: "create dest: " + cerr.Error(), Fatal: false})
	}

	total := fi.Size
	var writeErr error
	lastEmit := time.Now()
	derr := dev.GetObject(fi.ObjectId, f, func(sent int64) error {
		// Throttle progress to ~8 Hz; the driver renders its own cadence.
		if time.Since(lastEmit) < 120*time.Millisecond {
			return nil
		}
		lastEmit = time.Now()
		p := pct(sent, total)
		if e := em.send(serveEvent{Type: "progress", Remote: remote,
			Sent: sent, Total: total, Pct: &p}); e != nil {
			writeErr = e // driver pipe closed: abort the transfer
			return e
		}
		return nil
	})
	f.Close()

	if derr != nil {
		os.Remove(dest) // do not leave a partial file behind
		if writeErr != nil {
			// The driver went away; exit quietly rather than spamming a pipe.
			return true, writeErr
		}
		// A mid-stream MTP/USB error compromises the session: fatal.
		return true, em.send(serveEvent{Type: "error", Remote: remote,
			Error: "download: " + derr.Error(), Fatal: true})
	}

	// Report the number of bytes actually written; the driver re-checks the size
	// on disk against the inventory size and fails closed on any mismatch.
	nbytes := total
	if st, serr := os.Stat(dest); serr == nil {
		nbytes = st.Size()
	}
	return false, em.send(serveEvent{Type: "complete", Remote: remote, Dest: dest,
		Bytes: nbytes, Total: total})
}

func cmdServe(debug bool, storageWant uint32) {
	dev := openDevice(debug)
	defer mtpx.Dispose(dev)
	sid := pickStorage(dev, storageWant)

	em := newServeEmitter()
	if err := em.send(serveEvent{Type: "ready", Storage: sid, PID: os.Getpid()}); err != nil {
		return
	}

	scanner := bufio.NewScanner(os.Stdin)
	scanner.Buffer(make([]byte, 0, 64*1024), 4*1024*1024)
	for scanner.Scan() {
		line := scanner.Bytes()
		if len(line) == 0 {
			continue
		}
		var req serveRequest
		if err := json.Unmarshal(line, &req); err != nil {
			if e := em.send(serveEvent{Type: "error",
				Error: "bad request json: " + err.Error(), Fatal: false}); e != nil {
				return
			}
			continue
		}
		switch req.Cmd {
		case "quit":
			em.send(serveEvent{Type: "bye"})
			return
		case "ping":
			if err := em.send(serveEvent{Type: "pong"}); err != nil {
				return
			}
		case "pull":
			fatal, err := servePull(dev, sid, em, req.Remote, req.Dest)
			if fatal || err != nil {
				return
			}
		default:
			if err := em.send(serveEvent{Type: "error",
				Error: "unknown cmd: " + req.Cmd, Fatal: false}); err != nil {
				return
			}
		}
	}
	// stdin EOF (driver closed its end): dispose and exit cleanly.
}

func main() {
	debug := flag.Bool("debug", false, "enable MTP debug logging to stderr")
	storage := flag.Uint("storage", 0, "storage id (0 = first)")
	includeHidden := flag.Bool("all", false, "include hidden files/dirs (dot-prefixed); default skips them")
	flag.Parse()
	args := flag.Args()
	if len(args) == 0 {
		fail("usage: mtpinv [-storage <id>] [-all] [-debug] <storages|inventory|pull|serve> ...")
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
	case "serve":
		if len(args) != 1 {
			fail("usage: mtpinv -storage <id> serve  (reads NDJSON requests on stdin)")
		}
		cmdServe(*debug, uint32(*storage))
	default:
		fail("unknown subcommand %q", args[0])
	}
}
