# FilePromptForge
Build Prompts Programmatically and Write Responses to File. Allows for automated programmatic iteration of content.

I have a set of text files in folders.
my standard prompt is stored as a textfile
I want chatgpt api to go through each one,  read its contents and the standard prompt.
For each one, save the response to a textfile, named after the prompt text file.

Is this a program? GUI?
A powershell or python script?
is it a scripting language like autohotkey or lua?
can it be achived with just syntax at the command line?


its a thing you can call from the command line that allows you to 

send files as promopts to chatgpt INLINE other powershell comands. use the full suite of regex and scripting AND now chatgpt as a variable?



echo "text" > filename.txt
echo "chatgpt output" > filename.txt
chatgpt prompt "hello how many ares" + content of filename.text,  echo "chatgpt output" > NEWfilename.txt


as an example

for each file in \folders\ send-chatgpt: "Hello chatgpt, <contents of file1.txt> <contents of EACH file in c:\folder\"

for each response, Process text, write to text file. NAMING HAS OPTIONS. including overwriting the file it read from, (Overwrite means comment out the old words)

or commenting out and appending. 
or making duplicate structure, 
or changing the name of the old file .old.
Or programaticly naming, using the firs line sanitized.
or chatgpt can name the file (if instructed to do so) but inclduing it as its first line, then we scrape it for codeblocks and filter for filetypes?

that text file will be saved as a variable to be used in the next command 

