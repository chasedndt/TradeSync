import subprocess
import time
import os
import sys

def run_service(command, name):
    print(f"Starting {name}...")
    return subprocess.Popen(command, shell=True, stdout=sys.stdout, stderr=sys.stderr)

if __name__ == "__main__":
    # Ensure PYTHONPATH includes current directory
    os.environ["PYTHONPATH"] = os.getcwd()
    
    # Start Ingest Gateway
    ingest = run_service("uvicorn services.ingest-gateway.app.main:app --port 8080 --reload", "Ingest Gateway")
    
    # Start State API
    state = run_service("uvicorn services.state-api.app.main:app --port 8000 --reload", "State API")
    
    # Start Processor
    processor = run_service("python core/processor.py", "Event Processor")
    
    print("\nAll services started. Press Ctrl+C to stop.\n")
    print("Ingest Gateway: http://localhost:8080")
    print("State API: http://localhost:8000")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping services...")
        ingest.terminate()
        state.terminate()
        processor.terminate()
        print("Stopped.")
