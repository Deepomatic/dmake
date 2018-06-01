#ifndef __AMQP_H__
#define __AMQP_H__

//#include <string>
//#include <stdlib.h>
#include <amqp.h>
#include <SimpleAmqpClient/SimpleAmqpClient.h>

class AMQPWrapper
{
public:
    AMQPWrapper();

    void declareQueue(const std::string &queue);

    template<class T>
    bool recv(const std::string &queue, T &n);
    template<class T>
    bool recv(const std::string &queue, T &n, std::string &reply_queue);
    template<class T>
    void send(const std::string &queue, T n, const std::string &reply_queue = "");

private:
    AmqpClient::Channel::ptr_t _channel;
    std::map<std::string, std::string> _consumer_tags;
};

/*---------------------------------------------------------------------------*/

template<class T>
bool AMQPWrapper::recv(const std::string &queue, T &n)
{
    std::string reply_queue;
    return recv(queue, n, reply_queue);
}

/*---------------------------------------------------------------------------*/

template<class T>
bool AMQPWrapper::recv(const std::string &queue, T &n, std::string &reply_queue)
{
    const std::string consumer_tag = "";
    bool no_local = true;
    bool no_ack = true;
    bool exclusive = false;
    auto it = _consumer_tags.find(queue);
    if (it == _consumer_tags.end()) {
        it = _consumer_tags.emplace(queue, _channel->BasicConsume(queue, consumer_tag, no_local, no_ack, exclusive)).first;
    }

    amqp_bytes_t buffer;
    AmqpClient::Envelope::ptr_t message = _channel->BasicConsumeMessage(it->second);
    buffer = message->Message()->getAmqpBody();

    if (buffer.len != sizeof(n))
    {
        return false;
    }
    else
    {
        n = *((int*)buffer.bytes);
        reply_queue = message->Message()->ReplyTo();
        return true;
    }
}

/*---------------------------------------------------------------------------*/

template<class T>
void AMQPWrapper::send(const std::string &queue, T n, const std::string &reply_queue)
{
    // Prepare the message to send
    amqp_bytes_t body;
    body.len = sizeof(n);
    body.bytes = new char[body.len];
    body.bytes = memcpy(body.bytes, &n, body.len);

    amqp_basic_properties_t prop;
    prop._flags = 0;

    AmqpClient::BasicMessage::ptr_t message =
        AmqpClient::BasicMessage::Create(body, &prop);

    if (reply_queue != "") {
        message->ReplyTo(reply_queue);
    }

    _channel->BasicPublish("amq.direct", queue, message);
}

/*---------------------------------------------------------------------------*/

#endif
