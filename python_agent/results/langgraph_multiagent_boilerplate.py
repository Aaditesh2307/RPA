import operator
from typing import Annotated, Sequence, TypedDict

from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph import StateGraph, END

# 1. Define the State
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]

# 2. Define the Agents/Nodes
class Agent:
    def __init__(self, name: str, model: ChatOpenAI, system_prompt: str):
        self.name = name
        self.model = model
        self.system_prompt = system_prompt

    def __call__(self, state: AgentState):
        messages = state['messages']
        response = self.model.invoke([("system", self.system_prompt)] + messages)
        return {"messages": [response]}

# 3. Initialize LLM and Agents
llm = ChatOpenAI(model="gpt-4o")

researcher = Agent(
    name="Researcher",
    model=llm,
    system_prompt="You are an expert researcher. Provide detailed and accurate information."
)

writer = Agent(
    name="Writer",
    model=llm,
    system_prompt="You are a professional writer. Summarize the research into a concise report."
)

# 4. Define the Graph Logic
workflow = StateGraph(AgentState)

workflow.add_node("researcher", researcher)
workflow.add_node("writer", writer)

workflow.set_entry_point("researcher")
workflow.add_edge("researcher", "writer")
workflow.add_edge("writer", END)

app = workflow.compile()

if __name__ == "__main__":
    inputs = {"messages": [HumanMessage(content="Explain the benefits of multi-agent systems.")]}
    for output in app.stream(inputs):
        for key, value in output.items():
            print(f"Node '{key}':")
            print(value['messages'][-1].content)
            print("---")