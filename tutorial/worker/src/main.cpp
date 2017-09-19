#include <glog/logging.h>

#include "app.hpp"

int main(int argc, const char **argv)
{
    (void) argc;
    FLAGS_logtostderr = 1;
    google::InitGoogleLogging(argv[0]);

    bool stop = false;
    run(&stop, "worker");
    return 0;
}
