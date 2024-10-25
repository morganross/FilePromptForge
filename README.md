the gui calls and sends arguments to the installer
  the install_dir and the base_MD

the installer takes arguements and uses them to install the main.py, without arguements it uses the default values
  what is ment by install? create the default empty config file, set system path? is that it?

main.py accepts arguements and uses them to biuld a api request to openai, without arguements, it uses default values
  buiding a request requires flexable plus/minus equations. Maybe seperate logic file for the promot build logic
  for-each file-in-folder, folders are treated as "for each" file. 
 main.py can build a promot from arugements using prompt_build_logic, or from a file
files used for prompts can be specifyed inside of a file that the script then uses to send to api
or the prompt can be written into the arguement when running main. if writting it in, it becomes only add, and i wonder if it can do folders

superduper seperate logic funtions in a logic files or reach their own

text processor script runs on the response, it writes the resonse to disk
  it can trim before or after word or phrase or symbol or matched conent from other file, it can find replace, and it names the response file based on set rules,this part has regex.


  test function installs directories and files and sets apikey and makes a promot and writes a response using defaults
  
