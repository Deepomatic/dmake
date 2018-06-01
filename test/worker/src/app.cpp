#include <glog/logging.h>

#include "app.hpp"
#include "amqp_client.hpp"

/*---------------------------------------------------------------------------*/

// Tail recursive version
uint64_t factorial(int n, uint64_t acc = 1)
{
    if (n <= 1) {
        return acc;
    }
    else {
        return factorial(n - 1, acc * n);
    }
}

/*---------------------------------------------------------------------------*/

void run(bool *stop, std::string queue_name)
{
    AMQPWrapper amqp_client;
    amqp_client.declareQueue(queue_name);

    int n;
    std::string reply_queue;
    while(!*stop)
    {
        LOG(INFO) << "Waiting for a message on queue '" << queue_name << "'";
        if (amqp_client.recv(queue_name, n, reply_queue))
        {
            amqp_client.send(reply_queue, factorial(n));
        }
        else {
            LOG(ERROR) << "Bad message";
        }
    }
}

/*---------------------------------------------------------------------------*/
