#include <glog/logging.h>

#include "app.hpp"

int main(int argc, const char **argv)
{
    google::InitGoogleLogging(argv[0]);
    FLAGS_logtostderr = 1;

    bool stop = false;
    run(&stop, "worker");
    return 0;
}
