pip-clear-requirements:
	# => remove them before to update all dependencies
	rm -f requirements.txt

pip-freeze-update-all:
	# pip-compile minimizes changes when output already exists (no upgrade as condition from requirements.in is already met)
	# => remove it before to update all dependencies
	rm -f requirements.txt
	pip-compile --verbose --generate-hashes requirements.in -o requirements.txt

pip-freeze-update-minimal:
	# pip-compile minimizes changes when output already exists (no upgrade as condition from requirements.in are already met)
	# => just update minimal version in requirements.in before running this
	pip-compile --verbose --generate-hashes requirements.in -o requirements.txt
