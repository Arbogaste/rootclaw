[READ_ONLY_FILE DO NOT MODIFY]
Wave 0 (basic implementation)
- Start-up configuration
    - Extensions [.java, ...] (or regural expression as future feature)
    - .ignore file (like .gitignore)
    - accuracy intensity (1 = low accuracy, 3 = high accuracy)
    - Ollama or openrouter config
    - Main Model, and model fallbacks as lists 
    - Validation Model, and model fallbacks as lists (optional)
    - Notes (optional)

- Script starts out a specified directory dir/
set start_time = timestamp
    - then recursevely map the files to analyze
    - save the files as a list of files to analyze in a json file named [start_time]_[dir]_files_rc.json (x)
    - then read each file and save the results of the analysis in a json file named [start_time]_[filename]_rc.md (edge scenario = check if the lines of the files are more of the standard limit prefixed as safe, then split the file in chunks and analyze each chunk separately, then merge the results of the analysis in a single file named [start_time]_[filename]_rc.md)
    - validate coherence or retry to analyze if it's completly no-sense or not coherent with the project notes (optional)
    - based on the accuracy level, iterate more times on the same file to analyze
    it with less chunks or more context, using more thinking steps, use more validation steps.
    - then append the name of the file analyzed to the file dir/[start_time]_[dir]_analyzed_rc.txt
- When finished all the analysis append the timestamp of the end time analyis in the x file ([start_time]_[dir]_files_rc.json).

    
Before execution:
---dir/
    |--file1.py
    |--file2.go
    /script/
        |--script1.py
        |--script2.java
        /subscript/
            |--script3.php
            /subsubscript/
                |--script4.js
                
python3 root_claw.py [dir] [config_file]

Results after execution:
---dir/
    |--[start_time]_[file1_py]_rc.md
    |--[start_time]_[file2_go]_rc.md 
    |--[start_time]_[dir]_files_rc.json
    |--[start_time]_[dir]_analyzed_rc.txt
    |--file1.py
    |--file2.go
    /script/
        |--[start_time]_[script1_py]_rc.md 
        |--[start_time]_[script2_java]_rc.md 
        |--script1.py
        |--script2.java
        /subscript/
            |--[start_time]_[script3_php]_rc.md 
            |--script3.php
            /subsubscript/
                |--[start_time]_[script4_js]_rc.md
                |--script4.js
                |--script5.js  
                

Configuration Example [config.json] :
{
    "extensions": [".java", ".py", ".js", ".go", ".php"],
    "ignore": ["script5.js"],
    "ignore_file": "" #or fill with pathfile with patterns to ignore as .gitignore 
    "accuracy_intensity": 1,
    "ollama_config": {
        "model": "phi4:latest",
        "fallback_models": ["phi4:latest", "phi4:latest"],
        "validation_model": "phi4:latest",
        "validation_fallback_models": ["phi4:latest", "phi4:latest"],
        "notes": ""
    }
}


Critical points to address with robust logic and checks:
    - Chunking logic
    - Recursive logic to scan the files
    - error handling and retry logic
    - log without regression of performance
    - ollama connection and fallback logic
    - context used in the prompts to help the model to understand the project
    - how build best and best summary by summaries of summaries of the chunks of the file analyzed
    - validation prompts
    - validation model provided (optional)
    
