docker-deploy:
	@docker build . -t rancher:5000/timing2clockify:latest; \
    docker push rancher:5000/timing2clockify:latest; \
    ssh rancher@rancher docker pull rancher:5000/timing2clockify:latest; \
    curl -X POST http://rancher:9000/api/webhooks/1fab4db2-9459-489b-882a-6957c0030d96

docker-deploy-home:
	@docker build . -t 192.168.2.98:5000/timing2clockify:latest; \
    docker push 192.168.2.98:5000/timing2clockify:latest; \
    ssh rancher@192.168.2.98 docker pull rancher:5000/timing2clockify:latest; \
    curl -X POST http://192.168.2.98:9000/api/webhooks/1fab4db2-9459-489b-882a-6957c0030d96