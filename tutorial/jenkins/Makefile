all: build start

build:
	cp ../../requirements.txt .
	docker build -t dmake-jenkins-demo .

start:
	docker run -v `pwd`/jenkins_home:`pwd`/jenkins_home -e JENKINS_HOME=`pwd`/jenkins_home -v /tmp:/tmp -v /var/run/docker.sock:/var/run/docker.sock -p 8080:8080 --name dmake-jenkins-demo -d -i dmake-jenkins-demo

show:
	@docker exec -ti dmake-jenkins-demo cat /var/jenkins_home/secrets/initialAdminPassword