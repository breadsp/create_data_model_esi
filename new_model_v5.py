# -*- coding: utf-8 -*-
"""
Created on Tue Sep 16 09:11:25 2025

@author: breadsp2
"""

from langchain_core.prompts import PromptTemplate
import pandas as pd
import time
import re
import sys
from langchain_core.exceptions import OutputParserException
from langchain_neo4j import GraphCypherQAChain
from langchain_ollama import ChatOllama
from langchain_neo4j import Neo4jGraph
from langchain.callbacks.base import BaseCallbackHandler
from typing import Any #, Dict
from tabulate import tabulate
import streamlit as st
from streamlit_chat import message
from streamlit.components.v1 import html


#from langchain_core.callbacks import StdOutCallbackHandler

# Replace with your Neo4j connection details
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USERNAME = "neo4j"
NEO4J_PASSWORD = "aitestingdata2025"

# 1. Initialize your graph database connection
graph = Neo4jGraph(
    url=NEO4J_URI,
    username=NEO4J_USERNAME,
    password=NEO4J_PASSWORD
)

# 2. Get the schema
schema = graph.get_schema

#3. Load the training data which will be passed to the template
def convert_training_data(training_df):
    all_training_data = pd.DataFrame()
    for curr_dict in train_df:
        all_training_data = pd.concat([all_training_data, train_df[curr_dict]])
    
    all_training_data = all_training_data.drop_duplicates()
    all_training_data.reset_index(inplace=True, drop=True)
    return all_training_data

def create_examples_string(examples):
    examples_str = ""
    for row_idx in examples.index:
        examples_str += f"# {examples.loc[row_idx,'question']}\n{examples.loc[row_idx,'cypher']}\n\n"
    return examples_str

train_df = pd.read_excel(r"C:\Users\breadsp2\Desktop\olloma testing\sample_queries.xlsx", sheet_name=None)

all_training_data = convert_training_data(train_df)
cypher_examples_str = create_examples_string(all_training_data)    

################################################################################
#4. Create the template that will be used by the model
custom_cypher_prompt_template = """
You are an expert Cypher developer. Your task is to generate a valid Cypher query for a graph database based on the user's question and the provided schema.

Do not use fields that contain original or unit as these are place holders and not data

It is NOT possible to access variables that are not declared in a WITH statement
DO NOT add variables that were not requested for example
APPLY all filtering prior to calling a WITH statement

only is a key word and means to exclude all other values for the variable in question

If a variable is being counted, then ensure it is included in the return statement
Functions cannot be part of the where statement, use a with command 

if the question is asking for a specific participant count then use
match(s:study)-[]-(p:participant) with s, count(p) as part_count where part_count >= "users request"
return s.study_name, s.study_short_name as study_short_name, part_count as number_of_participants"

Do not use ` in the cypher response
Do not use a count filter, if none was asked for
Do not include variables that were not implied in the users question
If age is being requested, then take age_at_entrolment / 365 for the filter criteria

DO NOT USE the function lower()
If a WITH statement is used the only variables in the WITH statement can be passed onto the WHERE and RETURN statements

Always use the tolower() function to ensure case-insensitive matching for string variables.
Always use the tofloat() for numeric variables.
Always use the contains() function to ensure correct matching with the exception of sex or gender.

Do not make nodes that do not exist in the supplied model, the cypher is restricted by nodes and variables that already exist

If multiple conditions are asked, then each gets its own filter
If a participant does not have cancer, then p.participant_case_indicator = "No"
When a specific cancer or cancers are included in the question, make sure they are also included as part of the cypher filtering

Do not force the cypher to fit the question, if a term was asked that does not exist then return "unable to answer your question"

Schema:
{schema}

Cypher examples:
{cypher_examples}

Question: {query}
Cypher query:
        
Do not include any explanations or apologies in your response. 
Respond with a Cypher statement only!
"""
#################################################################################

prompt = PromptTemplate.from_template(custom_cypher_prompt_template)

#5. Remove variabes from the schema that serve as place holders and should not be used in any query
remove_list = ["type: STRING", "uuid: STRING", "study_id: FLOAT", "updated: DATE_TIME",
               "participant_id: STRING", "type: STRING", "uuid: STRING", "created: DATE_TIME", "age_at_first_cancer_diagnosis_original: FLOAT", 
               "age_at_enrollment_original: FLOAT", "age_at_first_cancer_diagnosis_original_unit: STRING", "age_at_enrollment_original_unit: STRING",
               "age_at_first_cancer_diagnosis_unit: STRING", "ncbi_taxonomy_id: INTEGER", "age_at_enrollment_unit: STRING"]

for i in remove_list:
    schema = schema.replace(i, "")
    
schema = schema.replace(", ,", ", ")

# Using a custom callback for better capture
class CypherErrorCallback(BaseCallbackHandler):
    def __init__(self):
        self.last_query = None
        
    def on_chain_start(self, serialized, inputs, **kwargs: Any) -> None:
        """Run when chain starts running."""
        print("\n")
        type_text("Chain started: please be patient while I analyize your request")
      
    def on_chain_end(self, output, **kwargs: Any) -> None:
        print("\n")
        type_text("Chain Finished: I have completed my analysis of the database, please see results below")

# 3. Create the full QA chain
my_callback = CypherErrorCallback()
chain = GraphCypherQAChain.from_llm(
    llm = ChatOllama(temperature=0, model="llama3.2"),
    graph=graph,
    #verbose=True,
    allow_dangerous_requests=True,
    cypher_prompt=prompt,
    validate_cypher=False,
    return_intermediate_steps=True,
    return_direct=True,
    callbacks=[my_callback])


def validate_natural_language_input(text_input: str) -> bool:
    """
    Validates the natural language input for basic safety and relevance.
    """
    error_msg = ""
    valid_query = True
    if not isinstance(text_input, str):
        error_msg = "Error: Input must be a string."
        valid_query = False
    if not text_input.strip():
        error_msg = "Error: Input cannot be empty."
        valid_query =  False
    if re.search(r'[;\'"]', text_input):
        error_msg = "Warning: Input contains potentially problematic characters. Please rephrase."
        valid_query =  False
    return curr_query, valid_query, error_msg

repeat_loop = True

def type_text(text, delay=0.05):
    print("AI Output: ", end='')
    for char in text:
        sys.stdout.write(char)  # Write the character to standard output
        sys.stdout.flush()      # Force the immediate display of the character
        time.sleep(delay)       # Pause for the specified delay
        
while repeat_loop:
    try:
        print("##################################################################")
        type_text("Welcome I am an AI program that can take a question, query my database and return an answer if applicable. \n")
        type_text('If you wish to quit please type exit or quit \n')
        type_text('How can I help you today? \n')
        print("User Input: ", end='')
        curr_query = input('')
        curr_query, valid_query, error_msg = validate_natural_language_input(curr_query)
        if curr_query.lower() in ['exit', 'quit']:
            repeat_loop = False
            break
        
        while valid_query is False:
            type_text("I am sorry the query you entered is not able to be processed. Please see message below")
            type_text(error_msg)
            curr_query = type_text("Please try your query again")
            print("User Input: ", end='')
            curr_query = input('')
            curr_query, valid_query, error_msg = validate_natural_language_input(curr_query)
        
        start_timer = time.perf_counter()
        results = chain.invoke({"query": curr_query, "schema": schema, "cypher_examples": cypher_examples_str})
        print("\n\n")
        result_df = pd.DataFrame(results["result"])
        result_df.drop_duplicates(inplace=True)    
       # print(f"the question that was asked:\n{results['question']}\n")
        print(f"The Generated Cypher Response:\n{results['intermediate_steps'][0]['query']}\n")
        
        if len(result_df) > 0:
            type_text("Tabulated output for the results of the cypher response")
            print("\n\n")
            print(tabulate(result_df, headers='keys', tablefmt="rounded_grid", maxcolwidths=30))
        else:
            type_text("Unfortunately I was not able to find any results that matched your question")
        
        end_timer = time.perf_counter()
        print(f"Your question took {end_timer - start_timer:.2f} seconds to process \n")
    except Exception as e:
        print(e)
        if isinstance(e, OutputParserException):
            print("check here")
    
        print("I was unable to generate a valid cyper query based on your question")
        print("Please check for spelling or filtering criteria to ensure the question was asked correctly")
    finally:
        if repeat_loop is True:
            answer = input("\nWould you like to ask another question?  ")
            if answer.lower() == 'yes':
                repeat_loop = True
            else:
                repeat_loop = False

print("thank you for using my program, hopefully I was able to answer all your questions")
print("Goodbye...")