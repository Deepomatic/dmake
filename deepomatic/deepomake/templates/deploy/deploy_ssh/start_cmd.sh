apt-get -v && export PKM=apt-get || export PKM=yum && \
docker --version || (sudo apt-key adv --keyserver hkp://p80.pool.sks-keyservers.net:80 --recv-keys 58118E89F3A912897C070ADBF76221572C52609D && echo "deb https://apt.dockerproject.org/repo ubuntu-$(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/docker.list - && sudo apt-get update && sudo apt-get install -y linux-image-extra-$(uname -r) linux-image-extra-virtual && sudo apt-get install -y docker-engine) && \
if [ -z "\`command -v unzip\`" ]; then sudo -E \$PKM update && sudo -E \$PKM -y install unzip curl nginx; fi && \
sudo service docker start || echo 'Already running' && \
sudo rm -rf ~/${APP_NAME} && \
unzip /tmp/deploy.zip -d ~/${APP_NAME} && \
rm /tmp/deploy.zip && \
cd ~/${APP_NAME} && \
sudo bash start_app.sh