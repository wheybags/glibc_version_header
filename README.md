# Glibc version header generator

Build portable Linux binaries, avoiding linker errors on users' older machines
due to incompatible glibc versions.

## What is this?

This is a tool that allows you to specify the glibc version that you want to
link against, regardless of what version is installed on your machine.
This allows you to make portable Linux binaries without having to build your
binaries on an ancient distribution (which is the current standard practice).

## Why would I want that?

So you can distribute a portable binary to your users. You know, on Windows,
you can just download a ZIP archive with a program in it, extract it,
double-click it, and the thing runs? Wouldn't it be nice if we could have that
on Linux?

There's no technical reason we can't - just standard practices that are hostile
to this goal. My particular interest is in using it for binaries of games,
but it's useful for all sorts of things.

## Why not just link glibc statically?

A statically linked binary doesn't work unless you have the same version of glibc
installed on the machine you run it on anyway. There is a
[workaround](https://sourceware.org/glibc/wiki/FAQ#Even_statically_linked_programs_need_some_shared_libraries_which_is_not_acceptable_for_me.__What_can_I_do.3F)
to this, but it has its disadvantages, so nobody does it.

## How does it work?

Glibc uses something called symbol versioning. For example, this means that when
you use `malloc` in your program, the symbol the linker will actually link
against is `malloc@GLIBC_YOUR_INSTALLED_VERSION` (actually, it will link to
malloc from the most recent version of glibc that changed the implementaton
of malloc, but you get the idea).

This means that when you run your old program on a newer system where malloc
has been changed, to say, take its size as a string instead of an integer,
that new crazy malloc will be `malloc@GLIBC_CRAZY_VERSION` but you'll still
link to `malloc@OLD_SANE_VERSION`, and glibc will keep exporting the old
symbol with a compatible implementation.

This effectively makes binaries forwards compatible, as the system will
always act like the version of glibc on the developers machine when they
build the binary. The downside of this is that if I compile my super cool
new program on my bleeding-edge Arch Linux machine, that binary is almost
useless to anyone who isn't cool enough to use the same new version of
glibc as me. I theorise that this is why almost no one ships Linux binaries -
it's just too much of a pain in the ass.

However, the version of a function that you link against _can_ be specified.
The GNU assembler has a "psuedo-op" `.symver SYM,SYM@VERSION`, which forces
the linker to use `SYM@VERSION` wherever you ask for `SYM`.
This can be embedded in C source like so:
`__asm__(".symver SYM,SYM@GLIBC_VERSION");`.

Great, but I want to use glibc 2.13 for my whole program, not just one function
in one translation unit. So, what can be done to resolve this is to generate a
header file that contains these symver asm blocks for every symbol exposed
by glibc. To do this, we build every version of glibc from 2.5 to the latest
version (please [open an issue](https://github.com/wheybags/glibc_version_header/issues/new)
if the latest version is out of date), check what symbols are exposed in all the
binaries built by that version (glibc splits the C standard library into a few
different binaries), and generate the header accordingly. Then, all you need
to do is make sure that header is included in every translation unit in your
build. This is as simple as adding `-include /path/to/glibc_version_header.h`
to your compiler flags using whatever build system you use.

### Does that actually work?

Yup, you just need to make sure all the binaries you're distributing are built
with the magic header. I've built GCC and binutils with this technique on
Debian 9 (glibc 2.24), and then run it successfully on
Ubuntu 12.04 (glibc 2.15). It's worked out of the box for everything I've tried
except building GCC itself, which required a little bit of messing because it
uses every obscure platform feature under the sun, many of which seem to have
been invented almost for its sole use.

## Caveats

It pretty much works out of the box for almost everything.
- Weak symbols don't work, you'll need to remove the entries for the functions
  you want weak references to. However, very few people use them, so you're
  probably fine.
- pthreads functions using wrong versions: If you use pthreads, you must use
  the `-pthread` flag, not `-lpthread`. You should be doing this anyway,
  however, so you're probably fine.
  - `-lpthread` just adds `libpthread.so` to your link flags, but the proper
    way is `-pthread`, which also defines the `_REENTRANT` flag, which lets the
    build *know* it's going to be linked to `libpthread.so`. This is important
    since libc has this horrible feature that pthreads functions are in
    `libpthread.so`, while the normal cstdlib functions are in `libc6.so`.
    However, a subset of pthreads functions are exposed in `libc6.so` as weak
    symbols with no-op implementations. This allows them to do a single compile
    of `libc6.so`, with appropriate locking calls added in to ensure thread
    safety where it should be ensured, but if you're not using threads
    (read: "didn't link `libpthread.so`"), the locking calls are no-ops.
    Because weak symbols don't work with this scheme, this messes up the link,
    so we only add the magic symver directives for these pthreads functions
    if `_REENTRANT` is defined.

## Usage

Just grab one of the [generated headers](version_headers/), and add it
to your compiler's C and C++ flags.

If using CMake, this would be:

```cmake
set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -include /path/to/header.h")
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -include /path/to/header.h")
```

If using autotools, just set your environment variables:

```bash
export CFLAGS="$CFLAGS -include /path/to/header.h"
export CXXFLAGS="$CXXFLAGS -include /path/to/header.h"
```

I would also recommend adding `-static-libgcc -static-libstdc++` as well.

## What glibc version should I use?

It depends on which distributions you want to target.
The oldest supported version is glibc 2.5, which was released in 2006.
That's probably ancient enough.

See the chart below for glibc versions found on common Linux distributions:

| Distribution | glibc version |
|--------------|---------------|
| Debian 7     | 2.13          |
| Debian 8     | 2.19          |
| Debian 9     | 2.24          |
| CentOS 6     | 2.12          |
| CentOS 7     | 2.17          |
| Ubuntu 14.04 | 2.19          |
| Ubuntu 16.04 | 2.23          |
| Ubuntu 18.04 | 2.27          |
