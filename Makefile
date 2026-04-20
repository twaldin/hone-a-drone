.PHONY: demo baseline setup clean

demo:
	.venv/bin/hone run controllers/planner.py --grader ./grader.sh --mutator claude-code:sonnet --budget 5

baseline:
	.venv/bin/python run_parallel.py --planner controllers/planner.py --levels 0 1 2 3 --seeds-per-level 3

setup:
	test -d sim/lsy_drone_racing/.git || git clone --depth 1 https://github.com/utiasDSL/lsy_drone_racing sim/lsy_drone_racing
	uv venv --python 3.11
	uv pip install -e "sim/lsy_drone_racing[sim]"
	uv pip install "git+https://github.com/twaldin/hone"
	uv pip install toppra

clean:
	rm -f runs/*.tmp runs/*.log
