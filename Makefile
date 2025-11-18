PYTHON_IMAGE := python:alpine

build:
	docker run -it --rm -v $(CURDIR):/src --workdir /src $(PYTHON_IMAGE) ./build.sh
