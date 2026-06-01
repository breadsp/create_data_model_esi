import streamlit as st
from openai import OpenAI
import mgclient
from langchain_memgraph.toolkits import MemgraphToolkit
from langchain_memgraph.graphs.memgraph import MemgraphLangChain
from langchain_openai import ChatOpenAI
from langchain_classic.agents import AgentExecutor,  create_openai_tools_agent #create_react_agent
from langchain_core.prompts import PromptTemplate # MessagesPlaceholder
from langchain_community.callbacks.streamlit import StreamlitCallbackHandler
from langchain_core.messages import HumanMessage, AIMessage
import pandas as pd

from gqlalchemy import Memgraph # type: ignore
import json
#import example_tools

# 1. Setup xAI / Grok Configuration
# You can get your API key from https://console.x.ai/

from pathlib import Path
import toml
import os

user_profile_path = Path.home()
config_path = os.path.join(user_profile_path , ".streamlit", "credentials.toml")

# Read the TOML file if it exists
if os.path.isfile(config_path):
    with open(config_path, "r") as f:
        config_data = toml.load(f)

XAI_API_KEY = config_data["API_Key"]["AIX_API_KEY"]
MEMGRAPH_USER = config_data["Memgraph_Creds"]["MEM_USER"]
MEMGRAPH_PASS = config_data["Memgraph_Creds"]["MEM_PASS"]


MEMGRAPH_HOST =  "127.0.0.1"
MEMGRAPH_PORT = 7687


default_model="grok-4-latest"

###########################################################################################
if "schema" not in st.session_state:    #gets the schema in json format
    memgraph = Memgraph(username=MEMGRAPH_USER, password=MEMGRAPH_PASS) # Or connect to your Memgraph instance
    result = memgraph.execute_and_fetch("SHOW SCHEMA INFO;")
    results = [i for i in result]
    st.session_state.schema = json.loads(results[0]["schema"])

if "cursor" not in st.session_state:    #adds memgraph cursor for querying
    conn = mgclient.connect(host=MEMGRAPH_HOST, port=MEMGRAPH_PORT, username=MEMGRAPH_USER, password=MEMGRAPH_PASS)
    st.session_state.cursor = conn.cursor()
    
if "model" not in st.session_state:   #creates the model to use
    st.session_state.model = ChatOpenAI(model=default_model, api_key=XAI_API_KEY,
                                        base_url="https://api.x.ai/v1", temperature = 0, streaming=True)

if "chat_memory" not in st.session_state:
    st.session_state.chat_memory = []

if "db" not in st.session_state:
    memgraph_url = f"bolt://{MEMGRAPH_HOST}:{MEMGRAPH_PORT}"
    st.session_state.db = MemgraphLangChain(
        url=memgraph_url,
        username=MEMGRAPH_USER,
        password=MEMGRAPH_PASS,
    )    
        
if "tools" not in st.session_state:
    toolkit = MemgraphToolkit(db=st.session_state.db, llm=st.session_state.model)
    tools = toolkit.get_tools()
    # Keep only run_cypher to avoid no-input tool signature issues with some model/agent combos.
    st.session_state.tools = [tool for tool in tools if tool.name != "run_cypher"]
    
if "list_of_tools" not in st.session_state:
    tool_names = [tool.name for tool in st.session_state.tools]
    st.session_state.list_of_tools = ', '.join(tool_names)
        
if "messages" not in st.session_state:
    # Start with a system prompt to define the agent's personality
    st.session_state.messages = [
        {"role": "system", 
         "content": "You are a database assistant. You have access to a Memgraph database and its tools. "
         "Translate natural language into Cypher queries, use the tools, and answer the user."
         }
    ]

###########################################################################################
st.set_page_config(page_title="Grok Chatbot", page_icon="🐦")
st.title("🐦 Powered by Grok")

# 3. Sidebar to manage session
with st.sidebar:
    if st.button("Reset Conversation"):
        st.session_state.messages = [
            {"role": "system", 
             "content": "You are a database assistant. You have access to a Memgraph database and its tools. "
                       "Translate natural language into Cypher queries, use the tools, and answer the user."
    }
   #         {"role": "system", "content": "You are Grok, a helpful AI with a sense of humor."}
        ]
        st.rerun()
    
# 4. Display chat history (skipping the system prompt for the UI)
for message in st.session_state.messages:
    if message["role"] != "system":
        with st.chat_message(message["role"]):
            st.markdown(message["content"])


def create_agent(tools, llm):
    template = '''You are an expert Open-Cypher data specialist who can generate complex queries based on user requirements to answer their questions using Open-Cypher.Answer the following questions as best you can in the form of a Cypher query. 
    
    You are a database deployment agent. You are strictly forbidden from writing a final Cypher query from memory. 

    To complete the user's request, you MUST execute your plan in this exact sequence:
        1. Call 'show_schema_info' to check the database layout.
        2. Call 'verify_query_against_memgraph_schema' to verify the users question is schema compliant.
    
    Always use the get_schema tool prior to atmepting to create a cypher
    
    
    
    Use the following format:
        
    Information:  Do not use GROUP BY in the final cypher statment
    Participant age is stored as age_at_enrollment
    Cancer Type is stored in primary_disease_site
    participant_id is stored in the participant node
    All nodes are lowercase and all relationships are lowercase
    Never use gender only use demographic.sex
    Don't use directional relationships in the cypher, the direction does not matter and can cause confusion for the model
    Stop using term and input the exact term asked for in the question when filtering, do not use a placeholder term
    
    
    Only use enough tools to generate the Cypher
        
    Cypher Rules:
        0) Use propery cypher syntax example match(prefix: node_name)
        1) When the variable is not a number then use the following filtering format WHERE ANY(term IN [term] WHERE tolower(variable) CONTAINS term) 
        2) lowercase all values expcet for the Cypher Key Words
        4) Do no use " in the return statement, use ` instead
        5) Do not use ≥ or ≤ , use >= or <= instead
        6) If the cypher has a WHERE statment, all variables must also be in the RETURN statement as an alias 
              (e.g., where WHERE f.study_short_name  RETURN WHERE f.study_short_name as study_name).
        7) Do not use collect in the cypher statment
        6) Always return a total count as number_of_records
        7) NULLS are not allowed, use = '' instead
        9) If the cypher has a WHERE statment, all variables must also be in the RETURN statement as an alias 
              (e.g., where WHERE f.study_short_name  RETURN WHERE f.study_short_name as study_name).
              
    Question: the input question you must answer
    Thought: you should always think about what to do
    Action: the action to take, should be one of [{tool_names}]
    Action Input: the input to the action
    Observation: the result of the action
    ... (this Thought/Action/Action Input/Observation can repeat N times)
    Thought: I now know the final answer and have the final cypher I need
    Final Answer: the final answer to the original input question
    
    Begin!

         
    Previous Conversation History:
    {chat_history}     
         
    Question: {input}
    Thought:{agent_scratchpad}'''

    prompt = PromptTemplate.from_template(template)
    
    agent = create_openai_tools_agent(llm, tools, prompt,  strict=True)
    #agent_executor = AgentExecutor(agent = agent, tools=tools, return_intermediate_steps=True)
    
    agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True, handle_parsing_errors=True,
                                   return_intermediate_steps=True) #, tool_choice="auto")
    return agent_executor

if "agent_executor" not in st.session_state:
    st.session_state.agent_executor = create_agent(st.session_state.tools, st.session_state.model)


def execute_cypher(cypher):
    st.session_state.cursor.execute(cypher)
    result = st.session_state.cursor.fetchall()
    columns = [desc.name for desc in st.session_state.cursor.description]
    df = pd.DataFrame(result, columns=columns)
    return df

# Display prior chat history from memory
for message in st.session_state.chat_memory:
    if isinstance(message, HumanMessage):
        st.chat_message("user").write(message.content)
    elif isinstance(message, AIMessage):
        st.chat_message("assistant").write(message.content)

# 5. Chat Input & Logic
if prompt := st.chat_input("Ask Grok something..."):
    # Show user message
    st.chat_message("user").markdown(prompt)
    validation_status = True
    #extracted_payload = example_tools.extract_entities_from_query(prompt, st.session_state.schema)

  #  st.write("here is my interpretation of the question")
  #  st.write(extracted_payload)


    # 4. Pass the payload directly into your tool
  #  st.write("--- Step 2: Running Tool Verification ---\n")
  #  validation_status, validation_result = example_tools.verify_query_against_memgraph_schema(
  #       extracted_payload,
  #       st.session_state.schema
  #  )
    if validation_status:
  #      st.write(extracted_payload)

        
        # Add to memory
        st.session_state.messages.append({"role": "user", "content": prompt})
    
        # Fetch response from Grok
        with st.chat_message("assistant"):
            response_placeholder = st.empty()
            full_response = ""
            
            try:
            # Create a visual callback container for the agent's thoughts
                st_callback = StreamlitCallbackHandler(st.container())
        
                # Pass the callback to the invoke method
                response = st.session_state.agent_executor.invoke(
                    {"input": prompt, "chat_history": st.session_state.chat_memory, "tool_names": st.session_state.list_of_tools
                     }, {"callbacks": [st_callback]}
                )
                #print("here is the full response")
                #print(response)
        
                # Write the final output
                st.write(response["output"])
                if response["output"].find("MATCH") == -1:
                    print("this is not a cypher")
                elif response["output"].find("MATCH") > 0:
                    print("match is found but in wrong spot? cypher starts with differnt key word")
                else:
                    df = execute_cypher(response["output"])
                    st.dataframe(df)
                
                
                st.session_state.chat_memory.append(HumanMessage(content=prompt))
                st.session_state.chat_memory.append(AIMessage(content=response["output"]))
                
            except Exception as e:
                st.error(f"Error connecting to Grok: {e}")
    else:
        st.write(validation_result)
        st.write("I am unable to process this question, please ask something else or rephrase")
