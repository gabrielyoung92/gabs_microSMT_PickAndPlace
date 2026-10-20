// Bare-metal newlib hooks: this firmware has no file descriptors or console.
// RS485 uses its own driver. snprintf/sscanf only operate on memory buffers.
// These signatures are the newlib ABI hooks, not an application-facing API.
// Return ENOSYS rather than pretending unsupported I/O succeeded; the linker
// may discard these functions when no file-backed stdio is actually used.
#include <errno.h>
#include <sys/types.h>

// No descriptors are opened by this firmware, so close is unsupported.
int _close(int fd) {
    (void)fd;
    errno = ENOSYS;
    return -1;
}

// There is no file/stream position to seek; leave the request unsuccessful.
off_t _lseek(int fd, off_t offset, int whence) {
    (void)fd;
    (void)offset;
    (void)whence;
    errno = ENOSYS;
    return (off_t)-1;
}

// Do not read RS485 here or touch the supplied buffer; this is unsupported I/O.
ssize_t _read(int fd, void* buffer, size_t length) {
    (void)fd;
    (void)buffer;
    (void)length;
    errno = ENOSYS;
    return -1;
}

// Do not send anything on RS485 here: a printf console would share/corrupt the
// feeder command bus. The caller receives an explicit unsupported-I/O failure.
ssize_t _write(int fd, const void* buffer, size_t length) {
    (void)fd;
    (void)buffer;
    (void)length;
    errno = ENOSYS;
    return -1;
}
