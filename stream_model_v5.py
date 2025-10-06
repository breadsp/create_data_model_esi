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
from neo4j import GraphDatabase

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USERNAME = "neo4j"
NEO4J_PASSWORD = "aitestingdata2025"

# 1. Initialize your graph database connection
graph = Neo4jGraph(
    url=NEO4J_URI,
    username=NEO4J_USERNAME,
    password=NEO4J_PASSWORD
)
driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD), encrypted=False)

# load the training data which will be passed to the template
#train_df = pd.read_excel(r"/Users/davenportaw/Projects/create_data_model_esi/sample_queries.xlsx")
def contains_edit_keywords(cypher_query):
    edit_keywords = [
        "CREATE", "MERGE", "SET", "DELETE", "REMOVE",
        "CREATE INDEX", "DROP INDEX", "CREATE CONSTRAINT", "DROP CONSTRAINT", "FOREACH"
    ]
    # Check for each keyword (case-insensitive)
    for kw in edit_keywords:
        if re.search(kw, cypher_query, re.IGNORECASE):
        #if re.search(rf"\b{kw}\b", cypher_query, re.IGNORECASE):
            print(f"{kw} was found in the cypher query")
            return True
    return False

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

def display_error_line(ex):
    trace = []
    tb = ex.__traceback__
    while tb is not None:
        trace.append({"filename": tb.tb_frame.f_code.co_filename,
                      "name": tb.tb_frame.f_code.co_name,
                      "lineno": tb.tb_lineno})
        tb = tb.tb_next
    print(str({'type': type(ex).__name__, 'message': str(ex), 'trace': trace}))

train_df = pd.read_excel(r"C:\Users\breadsp2\Desktop\olloma testing\sample_queries.xlsx", sheet_name=None)

all_training_data = convert_training_data(train_df)
cypher_examples_str = create_examples_string(all_training_data) 

################################################################################
# create the template that will be used by the model

custom_cypher_prompt_template = """
You are an expert Cypher developer. Your task is to generate a valid Cypher query for a graph database based on the user's question and the provided schema.

Do not use fields that contain original or unit as these are place holders and not data


It is NOT possible to access variables that are not declared in a WITH statement
DO NOT add variables that were not requested for example
APPLY all filtering prior to calling a WITH statement

If a variable is being counted, then ensure it is included in the return statement
Functions cannot be part of the where statement, use a with command 

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
    
every cypher should have a participant count in the return statement
    
Do not include any explanations or apologies in your response. 
Respond with a Cypher statement only!
"""
#################################################################################
#Use contains(x) for the following variables: race, ethnicity, cancer_diagnosis_primary_site and cancer_diagnosis_disease_morphology 

prompt = PromptTemplate.from_template(custom_cypher_prompt_template)

# 2. Get the schema
schema = graph.get_schema

# remove variabes from the schema that serve as place holders and should not be used in any query
remove_list = ["type: STRING", "uuid: STRING", "study_id: FLOAT", "updated: DATE_TIME",
               "participant_id: STRING", "type: STRING", "uuid: STRING", "created: DATE_TIME", "age_at_first_cancer_diagnosis_original: FLOAT", 
               "age_at_enrollment_original: FLOAT", "age_at_first_cancer_diagnosis_original_unit: STRING", "age_at_enrollment_original_unit: STRING",
               "age_at_first_cancer_diagnosis_unit: STRING", "ncbi_taxonomy_id: INTEGER", "age_at_enrollment_unit: STRING"]

for i in remove_list:
    schema = schema.replace(i, "")
    
schema = schema.replace(", ,", ", ")

# 3. Create the full QA chain
chain = GraphCypherQAChain.from_llm(
    llm = ChatOllama(temperature=0, model="llama3.2"),
    graph=graph,
    verbose=True,   #this prints the generated cypher, but does not save
    allow_dangerous_requests=True,
    cypher_prompt=prompt,
    validate_cypher=False,
    return_intermediate_steps=True,
    return_direct=True)

chain.cypher_query_corrector = None

def smart_wrap_code(code):
    # Add a newline before Cypher keywords
    keywords = ["MATCH", "WHERE", "WITH", "RETURN", "ORDER BY", "LIMIT",","]
    for kw in keywords:
        code = re.sub(rf"\s*{kw}\s*", f"\n{kw} ", code)
    return code
# 4. Invoke the chain with few-shot examples
#query_list = ["how many particpants are in each study?", "how many studies have at least 5000 male participants",
#              "summerize participant counts by sex and race"]
#query_list = ["How many participants have kidney cancer?",
#              "List all ethnicities for each study",
#              "How many particpants are female, black and between 35 and 45 years old?"
#             ]

def get_query_data(tx, query):
    result = tx.run(query)
    data_list = [i for i in result.data()]
    return data_list

if "repeat_loop" not in st.session_state:
    st.session_state.repeat_loop = True

st.write("Welcome I am an AI program that can take a question, query my database and return an answer if applicable")
st.write("How can I help you today?")

if st.session_state.repeat_loop:
    curr_query = ""
    cypher_query = ""
    curr_query = st.text_input("User Input:", key="user_input")
    if st.button("Submit Question"):
        try:
            #print("User question:", curr_query)
            start_timer = time.perf_counter()
            with st.spinner("Generating response..."):
                # keeps trying to run the query, but if invaid will cause an error
                results = chain.invoke({"query": curr_query, "schema": schema, "cypher_examples": cypher_examples_str})
                cypher_query = results['intermediate_steps'][0]['query']
                print(cypher_query)
                if contains_edit_keywords(cypher_query):
                    st.sidebar.warning("Edit keywords detected in Cypher query! Query will not be executed.")
                    st.write("Your query contains database editing commands and will not be run.")
                    print("Blocked query due to edit keywords:", cypher_query)
                else:
                    # Safe to run the query
                    st.sidebar.header("Generated Cypher Query")
                    wrapped_query = smart_wrap_code(cypher_query)
                    #print(wrapped_query)
                    st.sidebar.code(wrapped_query, language='cypher')
                    # ...run the query and display results as before...
                    try:
                        #print("Raw results:", results)
                        with driver.session() as session:
                            records = session.execute_read(get_query_data, cypher_query)
                            result_df = pd.DataFrame(records)
                            result_df.drop_duplicates(inplace=True)
                            if len(result_df) > 0:
                                st.write(result_df)
                            else:
                                st.write("Unfortunately I was not able to find any results for your question")
                    except Exception as e:
                        display_error_line(e)
                        st.write("Unfortunately the generated cypher query is not valid and I am not able to use it to answer your question")
                end_timer = time.perf_counter()
                st.write(f"Your question took {end_timer - start_timer:.2f} seconds to process \n")
        except Exception as e:
            display_error_line(e)
            # st.write("Exception:", e)
            st.write("I was unable to generate a valid cyper query based on your question")
            st.write("Please check for spelling or filtering criteria to ensure the question was asked correctly")
        # Ask if user wants to continue
        if st.button("Ask Another Question"):
            st.session_state.user_input = ""  # Clear input for next question
            st.session_state.repeat_loop = True
    if st.button("End Session"):
        #print("Failed to click the button")
        st.session_state.repeat_loop = False
if st.session_state.repeat_loop == False:
    st.write("thank you for using my program, hopefully I was able to answer all your questions")
    st.write("Goodbye...")
    st.stop()
    #print("thank you for using my program, hopefully I was able to answer all your questions")
    #print("Goodbye...")