pip-freeze-update-all: pip-clear-requirements pip-freeze-update-minimal

pip-clear-requirements:
	# => remove them before to update all dependencies
	rm -f requirements.txt
	rm -f requirements-dev.txt

pip-freeze-update-minimal:
	# pip-compile minimizes changes when output already exists (no upgrade as condition from requirements.in are already met)
	# => just update minimal version in requirements*.in before running this
	# you can also pass extra args to pip-compile, e.g.:
	#   make pip-freeze-update-minimal ARGS='-P botocore>=1.20.60'
	pip-compile --verbose --generate-hashes requirements.in -o requirements.txt $(ARGS)
	@>&2 echo 'WARNING: The modifications made to the requirements*.txt files will be applied at next dmake base image build. If you need them right now you can exit this shell and re-run dmake shell (or manually pip install (as root) these requirements*.txt files).'
