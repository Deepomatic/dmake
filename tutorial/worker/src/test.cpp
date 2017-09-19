#include <thread>

#include "gtest/gtest.h"
#include <glog/logging.h>

#include "amqp_client.hpp"
#include "app.hpp"

#define TEST_WORKER_QUEUE "test_worker"
#define TEST_REPLY_QUEUE "test_reply"

TEST(HelloWorld, TestQueue) {
    AMQPWrapper amqp_client;

    // Launch a thread to listen on the queue 'TEST_WORKER_QUEUE'
    bool stop = false;
    std::thread worker_thread(run, &stop, TEST_WORKER_QUEUE);

    // Wait for thread to start and declare 'TEST_WORKER_QUEUE'
    sleep(1);
    stop = true;

    // TEST_WORKER_QUEUE has been declared
    amqp_client.declareQueue(TEST_REPLY_QUEUE);
    amqp_client.send(TEST_WORKER_QUEUE, 6, TEST_REPLY_QUEUE);

    uint64_t     n;
    ASSERT_TRUE(amqp_client.recv(TEST_REPLY_QUEUE, n));
    ASSERT_EQ(720u, n);

    worker_thread.join();
}



int main(int argc, char **argv) {
    FLAGS_logtostderr = 1;
    google::InitGoogleLogging(argv[0]);

    ::testing::InitGoogleTest(&argc, argv);
    return RUN_ALL_TESTS();
}
