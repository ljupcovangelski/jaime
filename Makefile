# Makefile for Juju Charm Development (Mount-Safe Version)

PROJECT_NAME = jaime
BUILD_DIR = /tmp/charm-build-$(PROJECT_NAME)

.PHONY: help clean pack deploy

help:
	@echo "Available commands:"
	@echo "  make clean   - Clean up local build caches and temporary files"
	@echo "  make pack    - Safe-pack the charm natively outside the mount"
	@echo "  make deploy  - Pack and immediately deploy to the current Juju model"

clean:
	@echo "🧹 Cleaning up workspace..."
	rm -rf .venv/ .tox/ build/ *.charm
	rm -rf $(BUILD_DIR)

pack: clean
	@echo "📦 Copying workspace to native VM storage..."
	mkdir -p $(BUILD_DIR)
	# Copy source files to native disk, excluding virtual environments and logs
	rsync -avq . $(BUILD_DIR) --exclude .venv --exclude .tox --exclude .git --exclude build --exclude '*.charm'
	
	@echo "🔨 Packing charm on native filesystem..."
	cd $(BUILD_DIR) && charmcraft pack
	
	@echo "🚚 Pulling built charm back to mounted directory..."
	cp $(BUILD_DIR)/*.charm .
	@echo "✅ Success! Packed charm is ready."

deploy: pack
	@echo "🚀 Deploying charm to local Juju model..."
	juju deploy ./*.charm --force \
		--config provider="${JAIME_PROVIDER}" \
		--config model="${JAIME_MODEL}" \
		--config api-token="${JAIME_API_TOKEN}" \
		--config watch-statuses="error,blocked" \
		--config failure-timeout-minutes=1
	sleep 1
	juju relate jaime ${PRINCIPLE_CHARM} 

remove: 
	@echo "🧹 Removing the jaime charm from the local Juju model..."
	juju remove-relation jaime ${PRINCIPLE_CHARM}
	sleep 2
	juju remove-application jaime --no-prompt
