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
