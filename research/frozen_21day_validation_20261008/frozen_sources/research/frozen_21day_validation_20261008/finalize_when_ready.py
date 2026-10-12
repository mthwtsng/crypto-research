"""Run independent report checks after the complete frozen replay arrives."""
import json,pathlib,subprocess,time
P=pathlib.Path(__file__).resolve().parent
while not (P/'REPLAY_COMPLETE.json').exists():
 if (P/'PIPELINE_STOP.json').exists():raise RuntimeError('Pipeline stopped; repair recorded coverage error before reporting')
 time.sleep(30)
subprocess.run(['python3',str(P/'report_validation.py')],check=True)
