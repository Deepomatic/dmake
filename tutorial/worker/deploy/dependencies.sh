# Script will fail on any error
set -e

export PARALLEL_BUILD=${PARALLEL_BUILD:-8}
export MAKEFLAGS="${MAKEFLAGS} -j${PARALLEL_BUILD}"

apt-get update
apt-get --no-install-recommends -y install make cmake g++ wget tar

# RabbitMQ
apt-get --no-install-recommends -y install librabbitmq-dev

# Boost
apt-get --no-install-recommends -y install libboost-dev libboost-chrono-dev libboost-system-dev

# Google Logging
apt-get --no-install-recommends -y install libgoogle-glog-dev

cd /tmp

# RabbitMQ Client C v0.8.0
wget -O lib.tar.gz https://github.com/alanxz/rabbitmq-c/archive/v0.8.0.tar.gz
tar -zxvf lib.tar.gz
rm lib.tar.gz
d=`ls -d rabbitmq-c-*`
cd $d
apt-get --no-install-recommends -y install libssl-dev
cmake -DCMAKE_INSTALL_PREFIX:PATH=/usr .
make install
cd ..
rm -rf $d

# RabbitMQ Client C++ v2.4
wget -O lib.tar.gz https://github.com/alanxz/SimpleAmqpClient/archive/v2.4.0.tar.gz
tar -zxvf lib.tar.gz
rm lib.tar.gz
d=`ls -d SimpleAmqpClient-*`
cd $d
#sed -i -e "s/#define BROKER_HEARTBEAT 0/#define BROKER_HEARTBEAT 60/" src/ChannelImpl.cpp
cmake -DCMAKE_INSTALL_PREFIX:PATH=/usr .
make install
cd ..
rm -rf $d
