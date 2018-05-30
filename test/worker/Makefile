SHELL:=/bin/bash
prefix:=/usr/local

all:
	mkdir -p bin
	g++ --std=c++11 -o bin/worker src/main.cpp src/app.cpp src/amqp_client.cpp -lrabbitmq -lSimpleAmqpClient -lglog -Wall -Wextra
	g++ --std=c++11 -o bin/worker_test src/test.cpp src/app.cpp src/amqp_client.cpp gtest/gtest-all.cpp -lpthread -lrabbitmq -lSimpleAmqpClient -lglog -I. -Wall -Wextra -fsanitize=undefined -g

test:
	./bin/worker_test

install: all
	mkdir -p $(prefix)/bin
	cp -f ./bin/worker $(prefix)/bin/
	cp -f ./bin/worker_test $(prefix)/bin/
	mkdir -p $(prefix)/deploy
	cp -f ./deploy/{entrypoint.sh,start.sh,test-shared-volumes.sh} $(prefix)/deploy/
