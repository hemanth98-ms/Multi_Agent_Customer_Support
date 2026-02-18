from typing import Dict, Any
from agents.response_generator import ai_chain

class RequestRouter:
    """Routes and processes agent requests"""
    
    def route_request(self, request_data: Dict[str, Any]) -> str:
        """Route request based on type or content"""
        request_type = request_data.get('type', 'general')
        
        if request_type == 'support':
            return "Customer support inquiry"
        elif request_type == 'sales':
            return "Sales inquiry"
        elif request_type == 'technical':
            return "Technical support request"
        else:
            return "General inquiry"
    
    def process_request(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process incoming request and generate response"""
        try:
            context = self.route_request(request_data)
            data = request_data.get('data', '')
            history = request_data.get('history', '')
            
            response = ai_chain.generate_response(context, data, history)
            
            return {
                "status": "success",
                "response": response,
                "context": context
            }
        except Exception as e:
            return {
                "status": "error",
                "message": str(e)
            }

# Global instance
router = RequestRouter()