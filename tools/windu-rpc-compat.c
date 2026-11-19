/*
 * Keep Wind/U's automatically allocated SunRPC transports on loopback.
 * The GUI launcher preloads this adapter after starting rpcbind. Both
 * ELF classes are installed so the same $LIB path works in child tools.
 * Supplied sockets, RPC dispatch, credentials and registration are left
 * to the original transport factories. Ordinary bind() is not interposed.
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <netinet/in.h>
#include <stddef.h>
#include <sys/socket.h>
#include <unistd.h>

/* SVCXPRT stays opaque: the legacy libc and libtirpc own its layout. */
struct transport;
typedef struct transport *(*buffered_factory)(int, unsigned int, unsigned int);
typedef struct transport *(*udp_factory)(int);

static void *factory(const char *name)
{
    void *result = dlsym(RTLD_NEXT, name);

    /* Recent glibc retains SunRPC only as compatibility symbol versions. */
    if (!result) {
#if defined(__x86_64__)
        result = dlvsym(RTLD_NEXT, name, "GLIBC_2.2.5");
#elif defined(__i386__)
        result = dlvsym(RTLD_NEXT, name, "GLIBC_2.0");
#else
#error Build this adapter only for the ISE x86 library architectures.
#endif
    }
    if (!result)
        errno = ENOSYS;
    return result;
}

static int loopback_socket(int type, int protocol)
{
    struct sockaddr_in address = {
        .sin_family = AF_INET,
        .sin_addr.s_addr = htonl(INADDR_LOOPBACK),
    };
    int fd = socket(AF_INET, type, protocol);

    if (fd < 0)
        return -1;
    /* Match the vendor factories' reserved-port attempt and fallback. */
    if (bindresvport(fd, &address) < 0) {
        address.sin_port = 0;
        if (bind(fd, (struct sockaddr *)&address, sizeof(address)) < 0) {
            int saved_errno = errno;

            close(fd);
            errno = saved_errno;
            return -1;
        }
    }
    return fd;
}

static struct transport *buffered(const char *name, int fd,
                                  unsigned int send_size,
                                  unsigned int receive_size,
                                  int type, int protocol)
{
    buffered_factory original = factory(name);
    struct transport *result;
    int allocated = fd == -1;

    if (!original)
        return NULL;
    if (allocated) {
        fd = loopback_socket(type, protocol);
        if (fd < 0)
            return NULL;
    }
    result = original(fd, send_size, receive_size);
    if (!result && allocated) {
        int saved_errno = errno;

        /* The original factory does not own supplied fds on failure. */
        close(fd);
        errno = saved_errno;
    }
    return result;
}

struct transport *svctcp_create(int fd, unsigned int send_size,
                                unsigned int receive_size)
{
    return buffered("svctcp_create", fd, send_size, receive_size,
                    SOCK_STREAM, IPPROTO_TCP);
}

struct transport *svcudp_bufcreate(int fd, unsigned int send_size,
                                   unsigned int receive_size)
{
    return buffered("svcudp_bufcreate", fd, send_size, receive_size,
                    SOCK_DGRAM, IPPROTO_UDP);
}

struct transport *svcudp_create(int fd)
{
    udp_factory original = factory("svcudp_create");
    struct transport *result;
    int allocated = fd == -1;

    if (!original)
        return NULL;
    if (allocated) {
        fd = loopback_socket(SOCK_DGRAM, IPPROTO_UDP);
        if (fd < 0)
            return NULL;
    }
    result = original(fd);
    if (!result && allocated) {
        int saved_errno = errno;

        close(fd);
        errno = saved_errno;
    }
    return result;
}
