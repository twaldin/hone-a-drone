Generative AI tools used in development:
  - hone (https://github.com/twaldin/hone) — prompt/code optimizer, MIT
  - GEPA (https://github.com/gepa-ai/gepa) — reflective optimization engine, MIT
  - Claude Code (Anthropic) — code mutation engine

Open-source software included in Entry:
  - lsy_drone_racing (MIT) — simulation framework during development only
  - crazyflow (MIT) — simulation backend during development only
  - OpenVINS (Apache 2.0) — visual-inertial odometry
  - mav_trajectory_generation (Apache 2.0) — polynomial trajectory synthesis math (ported)
  - TOPP-RA (MIT) — time-optimal path parameterization
  - acados (BSD-2-Clause) — MPC solver
  - uav_geometric_control (Apache 2.0) — geometric attitude control reference
  - PyTorch, torchvision (BSD) — perception CNN runtime

Datasets used for training perception components:
  - UZH-FPV Drone Racing Dataset (research license, properly attributed)
  - TII-RATM Dataset (research use, properly attributed)

Environment:
  - Python 3.11, numpy, scipy, toppra (MIT)
  - sim/lsy_drone_racing (MIT) — proxy simulation, not part of submitted entry
