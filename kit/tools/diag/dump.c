/* Dump the loaded libSceSystemService launch function for static reading. */
#include <elf.h>
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>
#include <ps5/kernel.h>

static FILE *logf;

static void log_line(const char *fmt, ...) {
  va_list ap;
  va_start(ap, fmt);
  vfprintf(logf, fmt, ap);
  va_end(ap);
  fputc('\n', logf);
  fflush(logf);
}

static void dump_window(pid_t pid, intptr_t addr, size_t len, const char *dest) {
  unsigned char *buf = calloc(1, len);
  int rc;
  FILE *f;

  if (!buf) return;
  rc = kernel_proc_copyout(pid, addr, buf, len);
  log_line("copy 0x%llx len=0x%zx -> %d errno=%d",
           (unsigned long long)addr, len, rc, errno);

  f = fopen(dest, "wb");
  if (f) {
    fwrite(buf, 1, len, f);
    fclose(f);
    log_line("wrote %s", dest);
  } else {
    log_line("fopen %s failed: %d", dest, errno);
  }
  free(buf);
}

int main(void) {
  pid_t pid = getpid();
  intptr_t rootdir = kernel_get_proc_rootdir(pid);
  uint32_t handle = 0;
  intptr_t base, fn, fn2;
  int rc;

  kernel_set_proc_rootdir(pid, kernel_get_root_vnode());
  logf = fopen("/data/c09dump.txt", "w");
  if (!logf) return 1;

  log_line("== lnc dump ==");

  rc = kernel_dynlib_handle(pid, "libSceSystemService.sprx", &handle);
  log_line("dynlib_handle -> %d handle=%u", rc, handle);
  if (rc != 0) goto out;

  base = kernel_dynlib_mapbase_addr(pid, handle);
  fn = kernel_dynlib_dlsym(pid, handle, "sceLncUtilLaunchApp");
  fn2 = kernel_dynlib_dlsym(pid, handle, "sceLncUtilStartLaunchAppByTitleId");

  log_line("base=0x%llx", (unsigned long long)base);
  log_line("launch=0x%llx offset=0x%llx", (unsigned long long)fn,
           (unsigned long long)(fn - base));
  log_line("start =0x%llx offset=0x%llx", (unsigned long long)fn2,
           (unsigned long long)(fn2 - base));

  dump_window(pid, base, 0x1000, "/data/lnc_base.bin");
  if (fn) dump_window(pid, fn - 0x20, 0x1000, "/data/lnc_launch.bin");
  if (fn2) dump_window(pid, fn2 - 0x20, 0x1000, "/data/lnc_start.bin");

  {
    FILE *o = fopen("/data/lnc_offsets.txt", "w");
    if (o) {
      fprintf(o, "base=0x%llx\nlaunch=0x%llx\nstart=0x%llx\n",
              (unsigned long long)base, (unsigned long long)fn,
              (unsigned long long)fn2);
      fclose(o);
    }
  }

out:
  log_line("done");
  kernel_set_proc_rootdir(pid, rootdir);
  fclose(logf);
  return 0;
}
