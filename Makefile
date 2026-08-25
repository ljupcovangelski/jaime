# Makefile for Juju Charm Development

PROJECT_NAME = jaime
BUILD_DIR = /tmp/charm-build-$(PROJECT_NAME)

.PHONY: help clean pack pack-machine pack-k8s deploy

help:
	@echo "Available commands:"
	@echo "  make pack-machine  - Pack the machine subordinate charm"
	@echo "  make pack-k8s      - Pack the Kubernetes standalone charm"
	@echo "  make pack          - Pack both charms"
	@echo "  make clean         - Clean up build caches and temporary files"
	@echo "  make deploy        - Pack machine charm and deploy to current Juju model"

clean:
	rm -rf .venv/ .tox/ build/ *.charm
	rm -rf $(BUILD_DIR)
	rm -rf charms/machine/_jaime-package charms/k8s/_jaime-package

# Copy jaime-package into the charm directory, pack, then clean up.
# charmcraft's managed container only sees files inside the charm directory,
# so the shared library must be physically present (not a symlink) at pack time.

pack-machine: clean
	@echo "Packing machine charm..."
	cp -r jaime-package charms/machine/_jaime-package
	cd charms/machine && charmcraft pack
	cp charms/machine/*.charm .
	rm -rf charms/machine/_jaime-package
	@echo "Done: $$(ls -1 *.charm | grep -v k8s)"

pack-k8s: clean
	@echo "Packing k8s charm..."
	cp -r jaime-package charms/k8s/_jaime-package
	cd charms/k8s && charmcraft pack
	cp charms/k8s/*.charm .
	rm -rf charms/k8s/_jaime-package
	@echo "Done: $$(ls -1 *.charm | grep k8s || ls -1 *.charm)"

pack: pack-machine pack-k8s

deploy: pack-machine
	@echo "Deploying machine charm..."
	juju deploy ./jaime_ubuntu-24.04-amd64.charm --force \
		--config provider="${JAIME_PROVIDER}" \
		--config model="${JAIME_MODEL}" \
		--config api-token="${JAIME_API_TOKEN}" \
		--config watch-statuses="error,blocked" \
		--config failure-timeout-minutes=1
	sleep 1
	juju relate jaime ${PRINCIPLE_CHARM}

remove:
	@echo "Removing the jaime charm from the local Juju model..."
	juju remove-relation jaime ${PRINCIPLE_CHARM}
	sleep 2
	juju remove-application jaime --no-prompt
