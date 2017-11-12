import subprocess
import sys

def extract_versions_from_installed_folder(folder):
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
        
        # These are defined in both librt and libc, at different versions. file rt/Versions in glibc source refers to them being moved from
        # librt to libc, but left behind for backwards compatibility
        #if f.split("/")[-1].startswith("librt"):
        #    file_data = [x for x in file_data if not starts_with_any(x, {'clock_getcpuclockid', 'clock_nanosleep', 'clock_getres', 'clock_settime', 'clock_gettime' })]

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

def generate_header_string(syms):
    strings = ["#ifndef SET_GLIBC_LINK_VERSIONS_HEADER", "#define SET_GLIBC_LINK_VERSIONS_HEADER"]
    
    keys = syms.keys()
    keys.sort()

    for sym in keys:
        strings.append('__asm__(".symver ' + sym + ',' + sym + '@' + syms[sym] + '");')

    strings.append("#endif")

    return "\n".join(strings)

def __main__():
    syms = extract_versions_from_installed_folder(sys.argv[1])
    print generate_header_string(syms)

if __name__ == "__main__":
    __main__()
