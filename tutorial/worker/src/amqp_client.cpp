#include <glog/logging.h>

#include "amqp_client.hpp"

/*---------------------------------------------------------------------------*/

AMQPWrapper::AMQPWrapper()
{
    const char *var = "AMQP_URL";
    char *url = getenv(var);
    if (url == NULL)
    {
        LOG(FATAL) << "Could not find variable \"" << var << "\"";
    }
    int count = 0;
    while(true) {
        try {
            _channel = AmqpClient::Channel::CreateFromUri(url);
            break;
        }
        catch(const std::runtime_error &e) {
            if (count == 3) {
                LOG(ERROR) << "Giving up";
                throw;
            }
            LOG(ERROR) << "Connection failed, AMQP might not be ready. Retrying...";
            sleep(10);
            ++count;
        }
    }
}

/*---------------------------------------------------------------------------*/

void AMQPWrapper::declareQueue(const std::string &queue)
{
    _channel->DeclareQueue(queue);
    _channel->BindQueue(queue, "amq.direct", queue);
}

/*---------------------------------------------------------------------------*/
