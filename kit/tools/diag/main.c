/* Class of '09 PS5 launch diagnostics: report modes, fix permissions, dump klog. */
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>
#include <ps5/kernel.h>

static FILE *report;

static void log_line(const char *fmt, ...) {
  va_list ap;
  va_start(ap, fmt);
  vfprintf(report, fmt, ap);
  va_end(ap);
  fputc('\n', report);
  fflush(report);
}

static void stat_one(const char *path) {
  struct stat st;
  if (stat(path, &st) != 0) {
    log_line("STAT %-64s ERR %d (%s)", path, errno, strerror(errno));
    return;
  }
  log_line("STAT %-64s mode=%04o uid=%u gid=%u size=%lld", path,
           (unsigned)(st.st_mode & 07777), (unsigned)st.st_uid,
           (unsigned)st.st_gid, (long long)st.st_size);
}

static void fix_tree(const char *base, int depth) {
  DIR *dir;
  struct dirent *dp;
  char path[PATH_MAX + 1];

  if (depth > 8) return;
  dir = opendir(base);
  if (!dir) {
    log_line("OPENDIR %-58s ERR %d (%s)", base, errno, strerror(errno));
    return;
  }
  while ((dp = readdir(dir))) {
    struct stat st;
    if (!strcmp(dp->d_name, ".") || !strcmp(dp->d_name, "..")) continue;
    snprintf(path, sizeof(path), "%s/%s", base, dp->d_name);
    if (lstat(path, &st) != 0) continue;
    if (S_ISLNK(st.st_mode)) continue;
    if (S_ISDIR(st.st_mode)) {
      if (chmod(path, 0777) != 0)
        log_line("CHMOD %-63s DIR ERR %d (%s)", path, errno, strerror(errno));
      fix_tree(path, depth + 1);
    } else {
      if (chmod(path, 0777) != 0)
        log_line("CHMOD %-63s FILE ERR %d (%s)", path, errno, strerror(errno));
    }
  }
  chmod(base, 0777);
  closedir(dir);
}

static void dump_klog(void) {
  int fd = open("/dev/klog", O_RDONLY | O_NONBLOCK);
  char *buf;
  ssize_t total = 0;
  if (fd < 0) {
    log_line("KLOG open failed: %d (%s)", errno, strerror(errno));
    return;
  }
  buf = malloc(4 * 1024 * 1024);
  if (!buf) { close(fd); return; }
  for (;;) {
    ssize_t n = read(fd, buf + total, 4 * 1024 * 1024 - (size_t)total);
    if (n > 0) {
      total += n;
      if (total >= 4 * 1024 * 1024) break;
      continue;
    }
    if (n == 0) break;
    if (errno == EAGAIN || errno == EWOULDBLOCK) break;
    break;
  }
  close(fd);
  log_line("KLOG read %lld bytes", (long long)total);
  {
    FILE *k = fopen("/data/c09klog.txt", "wb");
    if (k) {
      fwrite(buf, 1, (size_t)total, k);
      fclose(k);
      log_line("KLOG written to /data/c09klog.txt");
    } else {
      log_line("KLOG write failed: %d (%s)", errno, strerror(errno));
    }
  }
  free(buf);
}

int main(void) {
  pid_t pid = getpid();
  intptr_t rootdir = kernel_get_proc_rootdir(pid);

  kernel_set_proc_rootdir(pid, kernel_get_root_vnode());

  report = fopen("/data/c09diag.txt", "w");
  if (!report) return 1;

  log_line("== Class of '09 launch diagnostics ==");

  stat_one("/data/homebrew/PPSA09009");
  stat_one("/data/homebrew/PPSA09009/eboot.bin");
  stat_one("/data/homebrew/PPSA09009/sce_sys");
  stat_one("/data/homebrew/PPSA09009/sce_sys/param.json");
  stat_one("/data/homebrew/PPSA09009/sce_module");
  stat_one("/data/homebrew/PPSA09009/sce_module/libc.prx");
  stat_one("/user/app/PPSA09009");
  stat_one("/user/app/PPSA09009/mount.lnk");
  stat_one("/user/appmeta/PPSA09009/param.json");
  stat_one("/system_ex/app/PPSA09009");
  stat_one("/system_ex/app/PPSA09009/eboot.bin");

  log_line("-- fixing permissions --");
  fix_tree("/data/homebrew/PPSA09009", 0);
  fix_tree("/user/app/PPSA09009", 0);
  fix_tree("/user/appmeta/PPSA09009", 0);

  log_line("-- after --");
  stat_one("/data/homebrew/PPSA09009/eboot.bin");
  stat_one("/data/homebrew/PPSA09009/sce_module/libc.prx");

  dump_klog();

  kernel_set_proc_rootdir(pid, rootdir);
  fclose(report);
  return 0;
}
