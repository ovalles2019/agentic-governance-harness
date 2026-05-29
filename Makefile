.PHONY: run serve demo clean

# Python interpreter (override with `make run PYTHON=python` if needed).
PYTHON ?= python3

# Regenerate all benchmark numbers from scratch.
run:
	$(PYTHON) -m harness.runner

# Run the harness, then serve the static dashboard at http://localhost:8000/dashboard.html
serve: run
	@echo "Open http://localhost:8000/dashboard.html"
	$(PYTHON) -m http.server 8000

# Launch the interactive live demo (the same app deployed on Render).
demo:
	@echo "Open http://localhost:8000"
	$(PYTHON) app.py

clean:
	rm -f results/results.json results/results.csv
