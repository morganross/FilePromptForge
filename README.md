environment variables
dictionaries
arguements
files


arguements are for people to use
otherwise it uses defaults or files

dont use defaults just for testing. may not need deaults everywhere

it uses dics to send info to other scripts?? no, use variables and files??


we will use all 3?
i would perfer to use only dics and args i think


the gui calls and sends arguments to the installer
  the install_dir and the base_MD

the installer takes arguements and uses them to install the main.py, without arguements it uses the default values
  what is ment by install? create the default empty config file, set system path? is that it?

main.py accepts arguements and uses them to biuld a api request to openai, without arguements, it uses default values
  buiding a request requires flexable plus/minus equations. Maybe seperate logic file for the promot build logic
  ########################################
## Adding Cartesian Products

**Understanding the Process:**

1. **Cartesian Product:** For two sets A and B, the Cartesian product A × B is the set of all ordered pairs (a, b)
2. **Element-wise Addition:** For each pair (a, b) in A × B, perform the operation a + b.

**Logical Description:**

* For every element in the first set:
  * For every element in the second set:
    * Add the current elements from both sets.
    * Store the result.

## Programming Libraries for Cartesian Product and Addition

Many programming languages have libraries or built-in functions that can efficiently handle Cartesian products and element-wise operations. Here are a few examples:

### Python:
* **itertools.product():** This function generates Cartesian products of iterable objects. You can then use a list comprehension or a generator expression to perform the addition.

```python
from itertools import product

def add_cartesian_products(set1, set2):
    return [a + b for a, b in product(set1, set2)]
```

##################################################3
* **Input:** Two sets of numbers.
* **Output:** A new set containing the sum of every combination of elements from the input sets.
* **Logic:** Create the Cartesian product of the two sets and then add the corresponding elements of each pair.
* **Efficiency:** If performance is critical, discuss the choice of algorithm and data structures.

By providing this information, the programmer should be able to effectively implement the function using the appropriate language and libraries.

  ########################################
 main.py can build a promot from arugements using prompt_build_logic, or from a file
files used for prompts can be specifyed inside of a file that the script then uses to send to api
or the prompt can be written into the arguement when running main. if writting it in, it becomes only add, and i wonder if it can do folders

superduper seperate logic funtions in a logic files or reach their own

text processor script runs on the response, it writes the resonse to disk
  it can trim before or after word or phrase or symbol or matched conent from other file, it can find replace, and it names the response file based on set rules,this part has regex.


  test function installs directories and files and sets apikey and makes a promot and writes a response using defaults
  
perfer arguements to env variables?

perfer files to argueents

maybe we dont need to store the text from inside the files at all, just condier them files untill the final step. 

the program should be very serialized at first
so maybe dont need to store anything, it goes one at a time using iter?




we are gunna use dictionaries
##################################################
## Other Ways to Store and Share Data in Python

While dictionaries are a versatile and popular choice, Python offers several other ways to store and share data:

### 1. **Variables:**
* **Direct assignment:** Assign values to variables within a script.
* **Global variables:** Declare variables outside of functions to make them accessible throughout the module.
* **Class attributes:** Store data within a class for object-oriented programming.

### 5. **Files:**
* Store data persistently on disk.
* Use functions like `open()` to read from and write to files.
* Common formats include text files, CSV files, JSON files, and more.
ases.

### 7. **Configuration Files:**
* Store key-value pairs in a structured format.
* Common formats include YAML, JSON, and INI.
* Use libraries like `yaml`, `json`, or `configparser` to parse and manipulate configuration files.

### 8. **Environment Variables:**
* Store system-wide settings that can be accessed by applications.
* Use the `os` module to access and modify environment variables.

**Choosing the best method depends on various factors, including:**

* **Data structure:** The type of data you need to store (e.g., key-value pairs, ordered lists, unique elements).
* **Persistence:** Whether you need to store data beyond the execution of a script.
* **Access:** How other parts of your application or system should access the data.
* **Performance:** The efficiency requirements for storing and retrieving data.

By understanding these options, you can select the most appropriate method for your specific use case and effectively manage data sharing in your Python projects.

