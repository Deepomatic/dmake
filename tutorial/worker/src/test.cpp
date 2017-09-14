#include <thread>

#include "gtest/gtest.h"
#include "amqp_client.hpp"
#include "app.hpp"

#define TEST_QUEUE "test_worker"

TEST(HelloWorld, TestQueue) {
    AMQPWrapper amqp_client;

    // Launch a thread to listen on the queue 'WORKER_QUEUE'
    bool stop = false;
    std::thread worker_thread(run, &stop);

    // Wait for thread to start and declare 'WORKER_QUEUE'
    sleep(1);
    stop = true;

    // WORKER_QUEUE has been declared
    amqp_client.declareQueue(TEST_QUEUE);
    amqp_client.send(WORKER_QUEUE, 6, TEST_QUEUE);

    uint64_t     n;
    ASSERT_TRUE(amqp_client.recv(TEST_QUEUE, n));
    ASSERT_EQ(720, n);

    worker_thread.join();
}