import subprocess
import sys
import os
import distutils.spawn
import copy
import shutil
import multiprocessing

basePath = os.path.dirname(os.path.realpath(__file__))

def extract_versions_from_installed_folder(folder, version):
    files = [x.strip() for x in subprocess.check_output("find '" + folder + "' -name \"*.so\"", shell=True).split()]

    def starts_with_any(str, set):
        for item in set:
            if str.startswith(item):
                return True
        return False

    data = []
    for f in files:

        # These are linker scripts that just forward to other .sos, not actual elf binaries
        if f.split("/")[-1] in {'libc.so', 'libm.so', 'libpthread.so'}:
            continue
        
        # Available versions will be listed in readelf output as function@GLIBC_version
        # Additionally, there will be a single function@@GLIBC_version entry, which defines the
        # default version.
        # See https://web.archive.org/web/20170124195801/https://www.akkadia.org/drepper/symbol-versioning section Static Linker
        command = "readelf -Ws '" + f + "' | grep \" [^ ]*@@GLIBC_[0-9.]*$\" -o"
        file_data = [x.strip() for x in subprocess.check_output([ '/bin/bash', '-c', 'set -o pipefail; ' + command]).split()]
       
        if version >= Version(2, 17) and version <= Version(2, 26):
            # These are defined in both librt and libc, at different versions. file rt/Versions in glibc source refers to them being moved from
            # librt to libc, but left behind for backwards compatibility
            if f.split("/")[-1].startswith("librt"):
                file_data = [x for x in file_data if not starts_with_any(x, {'clock_getcpuclockid', 'clock_nanosleep', 'clock_getres', 'clock_settime', 'clock_gettime' })]

        data += file_data


    syms = {}
    dupes = []

    for line in data:
        sym, ver = line.split("@@")

        if sym not in syms:
            syms[sym] = ver
        elif syms[sym] != ver:
            dupes.append(line)

    if len(dupes):
        raise Exception("duplicate incompatible symbol versions found: " + str(dupes))

    return syms

def generate_header_string(syms, missingFuncs):
    pthread_funcs_in_libc_so = {
        "pthread_attr_destroy",
        "pthread_attr_init",
        "pthread_attr_getdetachstate",
        "pthread_attr_setdetachstate",
        "pthread_attr_getinheritsched",
        "pthread_attr_setinheritsched",
        "pthread_attr_getschedparam",
        "pthread_attr_setschedparam",
        "pthread_attr_getschedpolicy",
        "pthread_attr_setschedpolicy",
        "pthread_attr_getscope",
        "pthread_attr_setscope",
        "pthread_condattr_destroy",
        "pthread_condattr_init",
        "pthread_cond_broadcast",
        "pthread_cond_destroy",
        "pthread_cond_init",
        "pthread_cond_signalpthread_cond_wait",
        "pthread_cond_timedwait",
        "pthread_equal",
        "pthread_exit",
        "pthread_getschedparam",
        "pthread_setschedparam",
        "pthread_mutex_destroy",
        "pthread_mutex_init",
        "pthread_mutex_lock",
        "pthread_mutex_unlock",
        "pthread_self",
        "pthread_setcancelstate",
        "pthread_setcanceltype",
        "pthread_attr_init",
        "__register_atfork",
        "pthread_cond_init pthread_cond_destroy",
        "pthread_cond_wait pthread_cond_signal",
        "pthread_cond_broadcast pthread_cond_timedwait"
    }

    pthread_symbols_used_as_weak_in_libgcc = {
        "pthread_setspecific",
        "__pthread_key_create",
        "pthread_getspecific",
        "pthread_key_create",
        "pthread_once"
    }
    pthread_symbols_used_as_weak_in_libstdcpp = {
       "pthread_setspecific",
       "pthread_key_delete",
       "__pthread_key_create",
       "pthread_once",
       "pthread_key_create",
       "pthread_getspecific",
       "pthread_join",
       "pthread_detach",
       "pthread_create"
    }

    strings = ["#if !defined(SET_GLIBC_LINK_VERSIONS_HEADER) && !defined(__ASSEMBLER__)", "#define SET_GLIBC_LINK_VERSIONS_HEADER"]
    
    for sym in sorted(syms.keys()):
        line = '__asm__(".symver ' + sym + ',' + sym + '@' + syms[sym] + '");'

        if sym in pthread_funcs_in_libc_so or sym in pthread_symbols_used_as_weak_in_libstdcpp or sym in pthread_symbols_used_as_weak_in_libgcc:
            line = "#ifdef _REENTRANT\n" + line + "\n#endif"
        if sym in pthread_symbols_used_as_weak_in_libgcc:
            line = "#ifndef IN_LIBGCC2\n" + line + "\n#endif"
        if sym in pthread_symbols_used_as_weak_in_libstdcpp:
            line = "#ifndef _GLIBCXX_SHARED\n" + line + "\n#endif"

        strings.append(line)

    for sym in sorted(list(missingFuncs)):
        strings.append('__asm__(".symver ' + sym + ',' + sym + '@GLIBC_WRAP_ERROR_SYMBOL_NOT_PRESENT_IN_REQUESTED_VERSION");')

    strings.append("#endif")

    return "\n".join(strings)

def apply_patches(glibcDir, version):
    patchesDir = basePath + "/patches"
    
    if version <= Version(2, 18):
        subprocess.check_call(["git", "apply", patchesDir + "/fix_bad_version_checks.diff"], cwd=glibcDir) 

def get_glibc_binaries(version):
    """
    Downloads and builds the specified version (git tag) of glibc.
    Returns the installed folder.
    """
    glibcDir = basePath + "/glibc"
    buildDir = basePath + "/builds/" + str(version) + "/build"
    installDir = basePath + "/builds/" + str(version) + "/install"

    if not os.path.exists(glibcDir):
        subprocess.check_call(["git", "clone", "git://sourceware.org/git/glibc.git", glibcDir], cwd=basePath)

    if not os.path.exists(installDir + "/build_succeeded"):
        subprocess.check_call(["git", "reset", "--hard", "HEAD"], cwd=glibcDir)
        subprocess.check_call(["git", "clean", "-dxf"], cwd=glibcDir)

        subprocess.check_call(["git", "checkout", str(version)], cwd=glibcDir)

        apply_patches(glibcDir, version)
        
        if os.path.exists(buildDir):
            shutil.rmtree(buildDir)
        os.makedirs(buildDir)

        if os.path.exists(installDir):
            shutil.rmtree(installDir)
        os.makedirs(installDir)
        
        env = copy.deepcopy(os.environ)
        env["CC"] = "gcc"

        jobString = "-j" + str(multiprocessing.cpu_count())

        subprocess.check_call([glibcDir + "/configure", "--disable-werror", "--disable-sanity-checks"], cwd=buildDir, env=env)
        subprocess.check_call(["make", jobString], cwd=buildDir)
        subprocess.check_call(["make", "install_root=" + installDir, "install", jobString], cwd=buildDir)

        with open(installDir + "/build_succeeded", "wb") as f:
            pass

    return installDir


def check_have_required_programs():
    requiredPrograms = ["gcc", "make", "git", "readelf", "grep"]
    
    missing = []

    for p in requiredPrograms:
       if distutils.spawn.find_executable(p) is None:
           missing.append(p)

    if len(missing):
        raise Exception("missing programs: " + str(missing) + ", please install via your os package manager")

class Version(object):
    def __init__(self, *args):
        if len(args) > 3 or len(args) < 2:
            raise Exception("invalid version: " + str(args))

        self.major = args[0]
        self.minor = args[1]

        if len(args) == 3:
            self.patch = args[2]
        else:
            self.patch = 0

    def version_as_str(self):
        s = str(self.major) + "." + str(self.minor)
        if self.patch != 0:
            s += "." + str(self.patch)

        return s

    def __str__(self):
        return "glibc-" + self.version_as_str()

    def __repr__(self):
        return self.__str__()

    def __lt__(self, other):
        return (self.major, self.minor, self.patch) < (other.major, other.minor, other.patch)

    def __le__(self, other):
        return (self.major, self.minor, self.patch) <= (other.major, other.minor, other.patch)

    def __gt__(self, other):
        return (self.major, self.minor, self.patch) > (other.major, other.minor, other.patch)

    def __ge__(self, other):
        return (self.major, self.minor, self.patch) >= (other.major, other.minor, other.patch)

    def __eq__(self, other):
        return (self.major, self.minor, self.patch) == (other.major, other.minor, other.patch)
    
    def __ne__(self, other):
        return (self.major, self.minor, self.patch) != (other.major, other.minor, other.patch)



def __main__():
    check_have_required_programs()

    supportedVersions = [
        Version(2, 13),
        Version(2, 14),
        Version(2, 14, 1),
        Version(2, 15),
        Version(2, 16),
        Version(2, 17),
        Version(2, 18),
        Version(2, 19),
        Version(2, 20),
        Version(2, 21),
        Version(2, 22),
        Version(2, 23),
        Version(2, 24),
        Version(2, 25),
        Version(2, 26)
    ]

    versionHeadersPath = basePath + "/version_headers"
    if os.path.exists(versionHeadersPath):
        shutil.rmtree(versionHeadersPath)
    
    syms = {}
    allsyms = set()
    for version in supportedVersions:
        print "generating data for version:", version
        installDir = get_glibc_binaries(version)
        syms[version] = extract_versions_from_installed_folder(installDir, version)
        allsyms = allsyms.union(set(syms[version].keys()))
    
    for version in supportedVersions:
        print "writing header for version:", version

        missingFuncs = allsyms - set(syms[version].keys())
        headerData = generate_header_string(syms[version], missingFuncs)

        if not os.path.exists(versionHeadersPath):
            os.makedirs(versionHeadersPath)
        
        with open(versionHeadersPath + "/force_link_glibc_" + version.version_as_str() + ".h", "wb") as f:
            f.write(headerData)

if __name__ == "__main__":
    __main__()
