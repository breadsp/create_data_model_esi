# -*- coding: utf-8 -*-
"""
Created on Mon Jan 12 12:31:44 2026

@author: breadsp2
"""

import streamlit as st
import mgclient
import pandas as pd
#from gqlalchemy import Memgraph

import os
from langchain_anthropic import ChatAnthropic

# Initialize Anthropic client
#ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_API_KEY = "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"
model = ChatAnthropic(model="claude-haiku-4-5-20251001", api_key=ANTHROPIC_API_KEY )


## load all necessary librarys to run this agent 
from langchain_memgraph.toolkits import MemgraphToolkit
import mgclient
from langchain_memgraph.graphs.memgraph import MemgraphLangChain
from langchain_classic.agents import AgentExecutor, create_react_agent
from langchain_core.prompts import PromptTemplate


# --- Memgraph Connection ---
# Assumes Memgraph is running on localhost:7687 without authentication
#@st.cache_resource
class Memgraph_DB():
    def __init__(self):
        self.host = "127.0.0.1"
        self.port =  7687
        self.username = ""
        self.password = ""
    def connect_to_db(self): 
        self.conn = mgclient.connect(host=self.host, port=self.port) #, username=self.username, password=self.password)
        self.cursor = self.conn.cursor()

def get_memgraph_client():
    """Establishes and caches a connection to Memgraph."""
    mem_db = Memgraph_DB()
    try:
        mem_db.connect_to_db()
    except Exception as e:
        st.error(f"Error connecting to Memgraph: {e}")
        return None
    return mem_db

if "mem_db" not in st.session_state:
     st.session_state.mem_db =  get_memgraph_client()
     memgraph_url = f"bolt://localhost:{st.session_state.mem_db.port}"
     db = MemgraphLangChain(url=memgraph_url, username=st.session_state.mem_db.username, password=st.session_state.mem_db.password)

def get_mem_tools(db):
    toolkit = MemgraphToolkit(db=db, llm=model)
    tools = toolkit.get_tools()
    tools = [tool for tool in tools if tool.name not in ["run_cypher"]]
    
    return tools

if "tools" not in st.session_state:
    st.session_state.tools =  get_mem_tools(db)
    
if "list_of_tools" not in st.session_state:
    tool_names = [tool.name for tool in st.session_state.tools]
    st.session_state.list_of_tools = ', '.join(tool_names)

def create_agent(tools, model):
    template = '''Answer the following questions as best you can. You have access to the following tools:
    
    {tools}
    
    Use the following format:
        
    Information:  Do not use GROUP BY in the final cypher statment
    Participant age is stored as age_at_enrollment
    Cancer Type is stored in primary_disease_site
    
    Question: the input question you must answer
    Thought: you should always think about what to do
    Action: the action to take, should be one of [{tool_names}]
    Action Input: the input to the action
    Observation: the result of the action
    ... (this Thought/Action/Action Input/Observation can repeat N times)
    Thought: I now know the final answer and have the final cypher I need
    Final Answer: the final answer to the original input question
    
    
    
    Begin!
    
    Question: {input}
    Thought:{agent_scratchpad}'''
    prompt = PromptTemplate.from_template(template)
    
    agent = create_react_agent(model, tools, prompt) # Using ReAct pattern
    
    agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=False, handle_parsing_errors=True,
                                   return_intermediate_steps=False, tool_choice="auto")
    return agent_executor
    
if "agent_executor" not in st.session_state:
    st.session_state.agent_executor = create_agent(st.session_state.tools, model)


# --- Streamlit UI ---
st.markdown("""
    <style>
        .block-container {
            padding-top: 1rem; /* Adjust this value to move higher/lower */
        }
        .centered-title { text-align: center;  margin-top: 0;
        }
    </style>
    """, unsafe_allow_html=True)

# Use markdown to render the title
st.markdown("<h1 class='centered-title'>Memgraph + Streamlit Example</h1>", unsafe_allow_html=True)

#st.title("Memgraph + Streamlit Example", text_alignment='center'))
st.set_page_config(layout="wide")

table_window = st.empty()
user_window = st.empty()


if st.session_state.mem_db:
#    st.success("Successfully connected to Memgraph!")
    memgraph_url = f"bolt://localhost:{st.session_state.mem_db.port}"
    db = MemgraphLangChain(url=memgraph_url, username=st.session_state.mem_db.username, password=st.session_state.mem_db.password)


    # Example 1: Count and display number of nodes
    try:
        st.session_state.mem_db.cursor.execute("MATCH (n) RETURN n.type as node_name, count(n) AS num_of_nodes;")
        qry_result = st.session_state.mem_db.cursor.fetchall()
        headers = [col.name for col in st.session_state.mem_db.cursor.description]
#        print(headers)
        df = pd.DataFrame(qry_result, columns=headers)
    
        with table_window.container(border=True):
            col_1, col_2, col_3 = st.columns([1, 1, 1])
            
            with col_1:
                styled_df = df[0:4].style.hide(axis="index")
                styled_df.set_table_styles([{'selector': '', 'props': [('font-size', '8px')]}])
                st.dataframe(styled_df, hide_index=True)
            with col_2:
                styled_df = df[5:9].style.hide(axis="index")
                styled_df.set_table_styles([{'selector': '', 'props': [('font-size', '8px')]}])
                st.dataframe(styled_df, hide_index=True)
            with col_3:
                styled_df = df[10:].style.hide(axis="index")
                styled_df.set_table_styles([{'selector': '', 'props': [('font-size', '8px')]}])
                st.dataframe(styled_df, hide_index=True)
              
    except Exception as e:
        print(e)

    # Example 2: Run a custom query and display results
    with user_window.container(border=True):
        user_1, out_2 = st.columns([1, 1])
        with user_1:
            st.session_state.user_query = st.text_area("Please enter your question here:")
        with out_2:
            if len(st.session_state.user_query) > 0:
                response = st.session_state.agent_executor.invoke({"input": st.session_state.user_query, "tools": st.session_state.tools,
                                                                   "agent_scratchpad": st.session_state.list_of_tools,
                                                  "system": "Pull the schema first to ensure you know what the nodes are and where properties are stored"})
                print("\n here is the final response \n")
                st.write(response["output"])
            else:
                st.write("waiting on user input....")


else:
    st.info("Waiting for Memgraph connection. Please ensure Memgraph is running.")
