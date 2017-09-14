all:
	mkdir -p bin
	g++ --std=c++11 -o bin/worker src/main.cpp src/app.cpp src/amqp_client.cpp -lrabbitmq -lSimpleAmqpClient -lglog
	g++ --std=c++11 -o bin/worker_test src/test.cpp src/app.cpp src/amqp_client.cpp gtest/gtest_main.cc gtest/gtest-all.cpp -lpthread -lrabbitmq -lSimpleAmqpClient -lglog -I.

test:
	./bin/worker_test