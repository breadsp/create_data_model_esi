# -*- coding: utf-8 -*-
"""
Created on Tue Sep 16 09:11:25 2025

@author: breadsp2
"""
from langchain_core.prompts import PromptTemplate # type: ignore
import pandas as pd
import time
import re
from langchain_neo4j import GraphCypherQAChain
from langchain_ollama import ChatOllama
from langchain_neo4j import Neo4jGraph
import streamlit as st
from neo4j import GraphDatabase

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USERNAME = "neo4j"
NEO4J_PASSWORD = "SubmitterData2025!"
#NEO4J_PASSWORD = "aitestingdata2025"

# Define a style block to center the title
title_alignment = """
    <style>
    .centered-title {
        text-align: center;
    }
    </style>
"""

st.markdown(title_alignment, unsafe_allow_html=True)
st.markdown(
        """
        <style>
        .block-container {
            padding-top: 0rem; /* Adjust this value as needed */
            padding-left: 1rem;
            padding-right: 1rem;
        }
        </style>
        """,
        unsafe_allow_html=True)

st.markdown("<h1 style='text-align: center; color: black; font-size: 30px;'>PopSci AI: Query Database from User Input</h1>", unsafe_allow_html=True)
########################################################
## this is where the program starts
st.text("Welcome, I am an AI program that can take your question and query my database.\n" +
         "If I am able to generate valid code I will return an answer to your question")
st.text("How can I help you today?")
placeholder = st.empty()
output_block = st.empty()

# 1. Initialize your graph database connection
if "graph" not in st.session_state:
    st.session_state.graph = Neo4jGraph(
        url=NEO4J_URI,
        username=NEO4J_USERNAME,
        password=NEO4J_PASSWORD
    )

if "driver" not in st.session_state:
    st.session_state.driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD), encrypted=False)

st.set_page_config(
    page_title="PopSci AI Interface: Text to Cypher",
    layout= "wide", #"centered",
    initial_sidebar_state="expanded")

st.sidebar.header("Users History")

###############################################################
## functions to use in the program
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

def correct_cypher(cypher_query):
    cypher_query = cypher_query.replace("participant_sex", "sex")
    cypher_query = cypher_query.replace("participant_race", "race")
    cypher_query = cypher_query.replace("participant_ethnicity", "ethnicity")
    cypher_query = cypher_query.replace("!=", "<>")
    cypher_query = cypher_query.replace('ANY(term IN ["cancer"] WHERE tolower(p.cancer_diagnosis_primary_site) CONTAINS term)', 
                                        "p.participant_case_indicator = 'Yes'")
    
    if "WITH s, COUNT(p) as Total_Participants" in cypher_query:
        cypher_query = cypher_query.replace("WITH s, COUNT(p) as Total_Participants","")
        cypher_query = cypher_query.replace("Total_Participants","COUNT(p) as Total_Participants")
    return cypher_query

def smart_wrap_code(code):
    # Add a newline before Cypher keywords
    keywords = ["MATCH", "WHERE", "WITH", "RETURN", "ORDER BY", "LIMIT",","]
    for kw in keywords:
        code = re.sub(rf"\s*{kw}\s*", f"\n{kw} ", code)
    return code

def get_query_data(tx, query):
    result = tx.run(query)
    data_list = [i for i in result.data()]
    return data_list

def update_side_bar(curr_query, cypher_query, curr_results):

    #st.sidebar.header("Users History")
    wrapped_query = smart_wrap_code(cypher_query)
    if len(curr_query):
        new_df = pd.DataFrame({"Query":[curr_query], "Cypher":[wrapped_query], "Results":[curr_results]})
        new_df = pd.concat([st.session_state.result_history, new_df])
        new_df = new_df.reset_index(drop=True)
        new_df.drop_duplicates("Query", keep="last", inplace=True)
        st.session_state.result_history = new_df
    
    if len(st.session_state.result_history) > 0:
        st.session_state.result_history.drop_duplicates("Query", keep="last", inplace=True)
    
        for curr_idx in st.session_state.result_history.index:  
            input_question = st.session_state.result_history.loc[curr_idx, "Query"]
            output_cypher = st.session_state.result_history.loc[curr_idx, "Cypher"]
            output_results = st.session_state.result_history.loc[curr_idx, "Results"]

            if len(input_question) > 0:
                try:
                    if(st.sidebar.button(input_question,  key= "question_" + str(curr_idx))):
                        print(f"question_{curr_idx} was pushed from update")
                except Exception as e:
                    pass  #function throws error on first pass, but works on second
                    print("unable to make new button?")
                    print(input_question)
                    print("question_" + str(curr_idx))
                #    st.sidebar.code(output_cypher, language='cypher')
                #    if len(output_results[0]) > 0:
                #        st.sidebar.dataframe(output_results[0])
                #    else:
                #        st.sidebar.write("No Results were found")
                #    ask_another()

            #st.sidebar.text(f"Users Question: \n {st.session_state.last_query[curr_idx]}")
                #st.sidebar.code(st.session_state.last_code[curr_idx], language='cypher')

def disable(status, new_question):
    st.session_state.input_disabled = status
    st.session_state.new_question = new_question

def toggle_another(status):
    st.session_state.another_disabled = status

def ask_another():
    if st.button("Ask Another Question",  key= "another_question",  on_click=disable, args=(False,True),
                 disabled = st.session_state.another_disabled):
        toggle_another(True)  #disable the ask another after clicking
        st.session_state.repeat_loop = True

def clear_input_box():
    st.session_state.user_input = ""  # Clear input for next question
    st.session_state.new_question = False
##################################################################
## convert training data into prompt format
if "cypher_examples_str" not in st.session_state:
    train_df = pd.read_excel(r"C:\Users\breadsp2\Desktop\olloma testing\sample_queries.xlsx", sheet_name=None)

    all_training_data = convert_training_data(train_df)
    st.session_state.cypher_examples_str = create_examples_string(all_training_data) 
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

prompt = PromptTemplate.from_template(custom_cypher_prompt_template)
schema = st.session_state.graph.get_schema

# remove variabes from the schema that serve as place holders and should not be used in any query
remove_list = ["type: STRING", "uuid: STRING", "study_id: FLOAT", "updated: DATE_TIME",
               "participant_id: STRING", "type: STRING", "uuid: STRING", "created: DATE_TIME", "age_at_first_cancer_diagnosis_original: FLOAT", 
               "age_at_enrollment_original: FLOAT", "age_at_first_cancer_diagnosis_original_unit: STRING", "age_at_enrollment_original_unit: STRING",
               "age_at_first_cancer_diagnosis_unit: STRING", "ncbi_taxonomy_id: INTEGER", "age_at_enrollment_unit: STRING"]

for i in remove_list:
    schema = schema.replace(i, "")
    
schema = schema.replace(", ,", ", ")

if "result_history" not in st.session_state:
    st.session_state.result_history = pd.DataFrame()

if "chain" not in st.session_state:
    st.session_state.chain = GraphCypherQAChain.from_llm(
        llm = ChatOllama(temperature=0, model="llama3.2"),
        #llm = ChatOllama(temperature=0, model="tomasonjo/llama3-text2cypher-demo"),
        
        graph=st.session_state.graph,
        verbose=True,   #this prints the generated cypher, but does not save
        allow_dangerous_requests=True,
        cypher_prompt=prompt,
        validate_cypher=False,
        return_intermediate_steps=True,
        return_direct=True)

    st.session_state.chain.cypher_query_corrector = None

if "repeat_loop" not in st.session_state:
    st.session_state.repeat_loop = True

if "input_disabled" not in st.session_state:
    st.session_state.input_disabled = False

if "another_disabled" not in st.session_state:
    st.session_state.another_disabled = True

if "new_question" not in st.session_state:
    st.session_state.new_question = False

with placeholder.container(border=True):
    if st.session_state.new_question == True:
        clear_input_box()
        print(f"input_var: {st.session_state.user_input}")
        toggle_another(True)
    if st.session_state.repeat_loop:
        curr_query = ""
        cypher_query = ""
        result_list = []

        #update_side_bar(curr_query, cypher_query, result_list, cypher_code, result_table)
        curr_query = st.text_input("User Input:", key="user_input",  disabled=st.session_state.input_disabled)  
        col_1, col_2, col_3 = st.columns([4,4,2], border=False)
        with col_1:
            if st.button("Submit Question", key= "sub_question", on_click=disable, args=(True,False,),
                        disabled=st.session_state.input_disabled):   #if clicked then disable input and button
                try:
                    toggle_another(True)
                    print("User question:", curr_query)
                    start_timer = time.perf_counter()
                    with st.spinner("Generating response..."):
                        # keeps trying to run the query, but if invaid will cause an error
                        results = st.session_state.chain.invoke({"query": curr_query , "schema": schema,
                                                                "cypher_examples": st.session_state.cypher_examples_str})
                        
                        #print("here are the results of the model")
                        #print(results)
                        cypher_query = results['intermediate_steps'][0]['query']
                        with output_block.container(border=True):
                            cypher_code, result_table = st.columns(2)
                            if contains_edit_keywords(cypher_query):
                                cypher_query = "Edit keywords detected in Cypher query! Query will not be executed."
                                #st.sidebar.warning("Edit keywords detected in Cypher query! Query will not be executed.")
                                with cypher_code:
                                    st.write("Your query contains database editing commands and will not be run.")
                                print("Blocked query due to edit keywords:", cypher_query)
                                result_list = ["Unable to process this input request"]
                            else:
                                cypher_query = correct_cypher(cypher_query)
                                wrapped_query = smart_wrap_code(cypher_query)
                                with cypher_code:
                                    st.markdown("<h3 style='font-size: 16px; color: black;'>Generated Cypher Query</h3>", unsafe_allow_html=True)
                                    st.code(wrapped_query)
                                try:
                                    #print("Raw results:", results)
                                    with st.session_state.driver.session() as session:
                                        print("here is the cypher:")
                                        print(cypher_query)

                                        records = session.execute_read(get_query_data, cypher_query)
                                        result_df = pd.DataFrame(records)
                                        result_df.drop_duplicates(inplace=True)
                                        result_list = [result_df]
                                        #update_side_bar(curr_query, cypher_query, [result_df])
                                        with result_table:
                                            if len(result_df) > 0:
                                                #st.header("Results: ")
                                                st.markdown("<h3 style='font-size: 16px; color: black;'>Query Results</h3>", unsafe_allow_html=True)
                                                st.write(result_df)
                                            else:
                                                st.markdown("<h3 style='font-size: 16px; color: black;'>Query Results</h3>", unsafe_allow_html=True)
                                                st.write("I was able to generate a valid cypher query")
                                                st.write("However, I was not able to find any results that matched your question")
                                except Exception as e:
                                    #display_error_line(e)
                                    with result_table:
                                        st.markdown("<h3 style='font-size: 16px; color: black;'>Query Results</h3>", unsafe_allow_html=True)
                                        st.write("Unfortunately the generated cypher query is not valid and I am not able to use it to answer your question")
                                    result_list = ["Generated query is invalid and not able to be run"]
                                    #update_side_bar(curr_query, "Unable to generate a valid cypher statment", ["Query was not run"])

                            end_timer = time.perf_counter()
                            update_side_bar(curr_query, cypher_query, result_list)
                            st.write(f"Your question took {end_timer - start_timer:.2f} seconds to process \n")
                            toggle_another(False)
                except Exception as e:
                    print("")
                    print(f"an error was found: {e}")
                    #display_error_line(e)
                    # st.write("Exception:", e)
                    #st.write("I was unable to generate a valid cyper query based on your question")
                    #st.write("Please check for spelling or filtering criteria to ensure the question was asked correctly")
                # Ask if user wants to continue
        with col_2:
                ask_another()
        with col_3:
            if st.button("End Session     " , key= "end_program",  on_click=disable, args=(True, True)):
                #user ended program, disable all buttons and inputs
                #print("Failed to click the button")
                st.session_state.repeat_loop = False
    if "result_history" in st.session_state.result_history:
        for curr_idx in st.session_state.result_history.index:  
            input_question = st.session_state.result_history.loc[curr_idx, "Query"]
            output_cypher = st.session_state.result_history.loc[curr_idx, "Cypher"]
            output_results = st.session_state.result_history.loc[curr_idx, "Results"]
            if(st.sidebar.button(input_question,  key= "question_" + str(curr_idx))):
                print(f"question_{curr_idx} was pushed from loop")
                with output_block.container(border=True):
                    cypher_code, result_table = st.columns(2)
                    with cypher_code:
                        st.markdown("<h3 style='font-size: 16px; color: black;'>Generated Cypher Query</h3>", unsafe_allow_html=True)
                        st.code(output_cypher)

                    with result_table:
                        st.markdown("<h3 style='font-size: 16px; color: black;'>Query Results</h3>", unsafe_allow_html=True)
                        st.write(output_results)

    if st.session_state.repeat_loop == False:
        st.write("Thank you for using my program, hopefully I was able to answer all your questions")
        st.write("Goodbye...")
        st.stop()
        #print("thank you for using my program, hopefully I was able to answer all your questions")
        #print("Goodbye...")