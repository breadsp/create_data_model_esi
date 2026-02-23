# -*- coding: utf-8 -*-
"""
Simple Memgraph AI Query Interface
"""

import streamlit as st

st.set_page_config(page_title="Memgraph AI Query", page_icon="🧠", layout="wide")
st.title("🧠 Memgraph AI Query Interface")

st.markdown("""
This interface allows you to query your Memgraph database using natural language.

**How to use:**
1. Enter a natural language question below
2. Click "Run Query" 
3. Claude will convert it to Cypher and execute it
""")

st.divider()

# Initialize agent only when needed
@st.cache_resource
def get_agent():
    """Lazy initialize agent only when first query is made"""
    from langchain_anthropic import ChatAnthropic
    from langchain_memgraph.toolkits import MemgraphToolkit
    from langchain_memgraph.graphs.memgraph import MemgraphLangChain
    from langchain_classic.agents import AgentExecutor, create_react_agent
    from langchain_core.prompts import PromptTemplate
    
    ANTHROPIC_API_KEY = "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"
    
    model = ChatAnthropic(model="claude-haiku-4-5-20251001", api_key=ANTHROPIC_API_KEY)
    db = MemgraphLangChain(url="bolt://localhost:7687", username="", password="")
    
    toolkit = MemgraphToolkit(db=db, llm=model)
    tools = toolkit.get_tools()
    tools = [t for t in tools if t.name != "run_cypher"]
    
    template = '''Answer the following questions as best you can. You have access to the following tools:

{tools}

Use the following format:

Question: the input question you must answer
Thought: you should always think about what to do
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now know the final answer
Final Answer: the final answer to the original input question

Begin!

Question: {input}
Thought:{agent_scratchpad}'''
    
    prompt = PromptTemplate.from_template(template)
    agent = create_react_agent(model, tools, prompt)
    executor = AgentExecutor(agent=agent, tools=tools, verbose=False, handle_parsing_errors=True, max_iterations=3)
    
    return executor, [t.name for t in tools]

# User input
user_query = st.text_area("🔍 Enter your question:", height=100, placeholder="e.g., How many participants are in the database?")

if st.button("🚀 Run Query", type="primary"):
    if not user_query:
        st.warning("Please enter a query")
    else:
        try:
            st.write("Loading agent...")
            executor, tool_names = get_agent()
            
            st.write("Running query...")
            result = executor.invoke({"input": user_query, "agent_scratchpad": ""})
            
            st.success("Query completed!")
            st.write(result.get("output", str(result)))
            
        except Exception as e:
            st.error(f"Error: {str(e)}")
            st.write(f"Full error: {type(e).__name__}")
