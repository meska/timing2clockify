docker-deploy:
	@docker build . -t 192.168.2.98:5000/timing2clockify:latest; \
    docker push 192.168.2.98:5000/timing2clockify:latest; \
    curl -X POST http://192.168.2.98:9000/api/webhooks/1fab4db2-9459-489b-882a-6957c0030d96
