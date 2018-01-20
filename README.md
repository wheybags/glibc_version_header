# Glibc version header generator
Build portable linux binaries, no more linker errors on user's older machines from incompatible glibc versions.

# What is this?
Essentially, this is a tool that allows you to specify the glibc version that you want to link against, regardless of what version is installed on your machine.
This allows you to make portable linux binaries, without having to build your binaries on an ancient distro (which is the current standard practice).

# Why would I want that?
So you can distribute a portable binary to your users. You know how on windows, you can just download a zip with a program in it, unzip, double click, and the thing runs? Wouldn't it be nice if we could have that on linux? 
There's no technical reason we can't, just standard practices that are hostile to this goal.
My particular interest is in using it for binaries of games, but it's useful for all sorts of things.

# Why not just static link glibc?
A statically linked binary doesn't work unless you have the same version of glibc installed on the machine you run it on anyway. There is a [workaround](https://sourceware.org/glibc/wiki/FAQ#Even_statically_linked_programs_need_some_shared_libraries_which_is_not_acceptable_for_me.__What_can_I_do.3F) to this, but it has its disadvantages, so noone does it.


# How does it work?
Glibc uses something called symbol versioning. This means that when you use eg, `malloc` in your program, the symbol the linker will actually link against is `malloc@GLIBC_YOUR_INSTALLED_VERSION` (actually, it will link to malloc from the most recent version of glibc that changed the implementaton of malloc, but you get the idea). 
This means that when you run your old program on a newer system, where malloc has been changed, to say, take it's size as a string instead of an integer, that new crazy malloc will be `malloc@GLIBC_CRAZY_VERSION` but you'll still link to `malloc@OLD_SANE_VERSION`, and glibc will keep exporting the old symbol with a compatible implementation.
This effectively make binaries forwards compatible, as the system will always act like the version of glibc on the developers machine when they build the binary.
The downside of this is that if I compile my super cool new program on my bleeding edge arch linux machine, that binary is almost useless to anyone who isn't cool enough to use the same new version of glibc as me. 
I theorise that this is why almost noone ships linux binaries - it's just too much of a pain in the ass.

However, the version of a function that you link against _can_ be specified.
The GNU assembler has a "psuedo-op" `.symver SYM,SYM@VERSION`, which forces the linker to use `SYM@VERSION` wherever you ask for `SYM`. 
This can be embedded in c source like so: `__asm__(".symver SYM,SYM@GLIBC_VERSION");`.
Great, but I want to use glib 2.13 for my whole program, not just one function in one translation unit.
So, what we do to resolve this, is we generate a header file that contains these symver asm blocks for every symbol exposed by glibc.
To do this, we build every version of glibc from 2.13 to current (open an issue if the latest version is no longer current please), check what symbols are exposed in all the binaries built by that version (glibc splits the c std lib into a few different binaries), and generate the header accordingly. 
Then, all you need to do is make sure that header is included in every translation unit in your build.
This is as simple as adding `-include /path/to/glibc_version_header.h` to your compiler flags using whatever build system you use.

## Does that actually work?
Yup, you just need to make sure all the binaries you're distributing are built with the magic header.
I've built gcc and binutils with this technique on debian 9 (glibc 2.24), and then run it successfully on ubuntu 12.04 (glibc 2.15).
It's worked out of the box for everything I've tried except building gcc itself, which required a little bit of messing, because it uses every obscure platform feature under the sun, many of which seem to have been invented almost for it's sole use.

# Caveats
It pretty much works out of the box for almost everything.
- Weak symbols don't work, you'll need to remove the entries for the functions you want weak references to. Almost noone uses them, however, so you're probably fine.
- pthreads functions using wrong versions: If you use pthreads, you must use the -pthread flag, not -lpthread. You should be doing this anyway, however, so you're probably fine.
  -lpthread just adds libpthread.so to your link flags, but the proper way is -pthread, which also defines the `_REENTRANT` flag, which lets the build _know_ it's going to be linked to libpthread.so. This is important since libc has this horrible feature that pthreads functions are in libpthread.so, while the normal cstdlib functions are in libc6.so. However, a subset of pthreads functions are exposed in libc6.so as weak symbols, with noop implementations. This allows them to do a single compile of libc6.so, with appropriate locking calls added in to ensure thread safety where it should be ensured, but if you're not using threads (read - didn't link libpthread.so), the locking calls are noops. 
  Because weak symbols don't work with this scheme, this messes up the link, so we only add the magic symver directives for these pthreads functions if `_REENTRANT` is defined.

# Usage
Just grab one of the [generated headers](version_headers), and add it to your compile flags.
In cmake, this would be:
```cmake
set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -include /path/to/header.h")
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -include /path/to/header.h")
```

For autotools, just set your env vars:
```bash
export CFLAGS="$CFLAGS -include /path/to/header.h"
export CXXFLAGS="$CXXFLAGS -include /path/to/header.h"
```

I would also recommend adding `-static-libgcc -static-libstdc++` as well.

# What glibc version should I use then?
Depends on who you want to target. The oldest supported version is glibc 2.13, which is the version used in ubuntu 11.04. That's probably ancient enough.



