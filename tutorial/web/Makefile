run:
	./deploy/web/run/start.sh

pip-freeze-update-all:
	$(MAKE) -C deploy/base/build/ $@

pip-freeze-update-minimal:
	# pip-compile minimizes changes when output already exists (no upgrade as condition from requirements.in are already met)
	# you can also pass extra args to pip-compile, e.g.:
	#   make pip-freeze-update-minimal ARGS='-P botocore>=1.20.60'
	$(MAKE) -C deploy/base/build/ $@
