import uuid
from typing import Dict, List, Any, TypedDict

class AgentContext(TypedDict):
    job_id: str
    customer_info: Dict[str, Any]
    vehicle_details: Dict[str, Any]
    diagnostics: List[str]
    parts_required: List[str]
    status: str

class BaseAgent:
    def __init__(self, name: str):
        self.name = name

    def process(self, context: AgentContext) -> AgentContext:
        raise NotImplementedError

class ServiceAdvisor(BaseAgent):
    def process(self, context: AgentContext) -> AgentContext:
        print(f"[{self.name}] Intake: Processing customer request for {context['vehicle_details']['model']}")
        context['status'] = 'Intake Complete'
        return context

class Technician(BaseAgent):
    def process(self, context: AgentContext) -> AgentContext:
        print(f"[{self.name}] Diagnostics: Inspecting vehicle {context['job_id']}")
        context['diagnostics'].append('Brake pads worn out')
        context['parts_required'].append('Brake Pad Set')
        context['status'] = 'Diagnostics Complete'
        return context

class PartsManager(BaseAgent):
    def process(self, context: AgentContext) -> AgentContext:
        print(f"[{self.name}] Inventory: Checking availability for {context['parts_required']}")
        context['status'] = 'Parts Ordered'
        return context

class MechanicShopOrchestrator:
    def __init__(self):
        self.nodes = {
            'intake': ServiceAdvisor("Advisor_1"),
            'diagnostics': Technician("Tech_1"),
            'parts': PartsManager("Parts_1")
        }
        self.workflow = ['intake', 'diagnostics', 'parts']

    def run(self, customer_data: Dict, vehicle_data: Dict):
        context: AgentContext = {
            'job_id': str(uuid.uuid4()),
            'customer_info': customer_data,
            'vehicle_details': vehicle_data,
            'diagnostics': [],
            'parts_required': [],
            'status': 'Started'
        }

        for node_key in self.workflow:
            agent = self.nodes[node_key]
            context = agent.process(context)
        
        return context

if __name__ == '__main__':
    shop = MechanicShopOrchestrator()
    final_state = shop.run(
        customer_data={'name': 'John Doe', 'phone': '555-0123'},
        vehicle_data={'make': 'Toyota', 'model': 'Camry', 'year': 2020}
    )
    print(f"\nFinal Job Status: {final_state['status']}")
    print(f"Diagnostics: {final_state['diagnostics']}")