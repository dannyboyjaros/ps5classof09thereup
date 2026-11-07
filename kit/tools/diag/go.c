/* Class of '09 PS5 launch driver: write param.json, launch the title, dump klog. */
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

extern int sceLncUtilInitialize(void);
extern int sceLncUtilLaunchApp(const char *title_id, const char **argv, void *param);

static const char PARAM_JSON[] =
"{\n"
"  \"ageLevel\": {\n"
"    \"default\": 0\n"
"  },\n"
"  \"applicationCategoryType\": 0,\n"
"  \"applicationDrmType\": \"free\",\n"
"  \"attribute\": 1644167168,\n"
"  \"attribute2\": 0,\n"
"  \"attribute3\": 1048576,\n"
"  \"conceptId\": \"09009\",\n"
"  \"contentBadgeType\": 1,\n"
"  \"contentId\": \"UP0000-PPSA09009_00-CLASS0909PS5HOME\",\n"
"  \"contentVersion\": \"01.000.000\",\n"
"  \"downloadDataSize\": 256,\n"
"  \"gameIntent\": {\n"
"    \"permittedIntents\": [\n"
"      {\n"
"        \"intentType\": \"launchActivity\"\n"
"      }\n"
"    ]\n"
"  },\n"
"  \"localizedParameters\": {\n"
"    \"defaultLanguage\": \"en-US\",\n"
"    \"en-US\": {\n"
"      \"titleName\": \"Class of '09\"\n"
"    }\n"
"  },\n"
"  \"masterVersion\": \"01.00\",\n"
"  \"pubtools\": {\n"
"    \"creationDate\": \"2026-11-05 00:00:00\",\n"
"    \"loudnessSnd0\": \"-28.00\",\n"
"    \"toolVersion\": \"2.00\"\n"
"  },\n"
"  \"requiredSystemSoftwareVersion\": \"0x0000000000000000\",\n"
"  \"sdkVersion\": \"0x0000000000000000\",\n"
"  \"titleId\": \"PPSA09009\",\n"
"  \"versionFileUri\": \"\"\n"
"}\n";

static FILE *logf;

static void log_line(const char *fmt, ...) {
  va_list ap;
  va_start(ap, fmt);
  vfprintf(logf, fmt, ap);
  va_end(ap);
  fputc('\n', logf);
  fflush(logf);
}

static int write_file(const char *path) {
  FILE *f = fopen(path, "wb");
  if (!f) {
    log_line("WRITE %-60s OPEN ERR %d (%s)", path, errno, strerror(errno));
    return -1;
  }
  if (fwrite(PARAM_JSON, 1, sizeof(PARAM_JSON) - 1, f) != sizeof(PARAM_JSON) - 1) {
    log_line("WRITE %-60s SHORT ERR %d (%s)", path, errno, strerror(errno));
    fclose(f);
    return -1;
  }
  fflush(f);
  fclose(f);
  chmod(path, 0777);
  log_line("WRITE %-60s OK (%u bytes)", path, (unsigned)(sizeof(PARAM_JSON) - 1));
  return 0;
}

static void dump_klog(const char *dest) {
  int fd = open("/dev/klog", O_RDONLY | O_NONBLOCK);
  char *buf;
  ssize_t total = 0;

  if (fd < 0) {
    log_line("KLOG open failed: %d (%s)", errno, strerror(errno));
    return;
  }
  buf = malloc(8 * 1024 * 1024);
  if (!buf) {
    close(fd);
    return;
  }
  for (;;) {
    ssize_t n = read(fd, buf + total, 8 * 1024 * 1024 - (size_t)total);
    if (n > 0) {
      total += n;
      if (total >= 8 * 1024 * 1024) break;
      continue;
    }
    break;
  }
  close(fd);

  {
    FILE *k = fopen(dest, "wb");
    if (k) {
      fwrite(buf, 1, (size_t)total, k);
      fclose(k);
      log_line("KLOG %lld bytes -> %s", (long long)total, dest);
    } else {
      log_line("KLOG write %s failed: %d (%s)", dest, errno, strerror(errno));
    }
  }
  free(buf);
}

int main(void) {
  pid_t pid = getpid();
  intptr_t rootdir = kernel_get_proc_rootdir(pid);
  int ret;

  kernel_set_proc_rootdir(pid, kernel_get_root_vnode());

  logf = fopen("/data/c09go.txt", "w");
  if (!logf) return 1;

  log_line("== Class of '09 launch driver ==");

  mkdir("/user/app/PPSA09009", 0777);
  mkdir("/user/app/PPSA09009/sce_sys", 0777);
  mkdir("/user/appmeta/PPSA09009", 0777);
  mkdir("/data/homebrew/PPSA09009/sce_sys", 0777);

  write_file("/data/homebrew/PPSA09009/sce_sys/param.json");
  write_file("/user/app/PPSA09009/sce_sys/param.json");
  write_file("/user/appmeta/PPSA09009/param.json");

  dump_klog("/data/c09klog_before.txt");

  ret = sceLncUtilInitialize();
  log_line("sceLncUtilInitialize -> %d (0x%08x)", ret, (unsigned)ret);

  ret = sceLncUtilLaunchApp("PPSA09009", NULL, NULL);
  log_line("sceLncUtilLaunchApp -> %d (0x%08x)", ret, (unsigned)ret);

  sleep(6);
  dump_klog("/data/c09klog_after.txt");
  log_line("done");

  kernel_set_proc_rootdir(pid, rootdir);
  fclose(logf);
  return 0;
}
