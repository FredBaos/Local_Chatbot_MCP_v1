from flask import Flask, render_template, request, jsonify
from mlx_lm import load, generate
import mlx.core as mx

app = Flask(__name__)

mx.set_default_device(mx.Device(mx.gpu))
model, tokenizer = load("mlx-community/Llama-3.2-3B-Instruct-4bit")

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze():
    data = request.get_json()
    user_text = data.get("text", "")
    
    if not user_text:
        return jsonify({"error": "No text provided"}), 400
        
    try:
        messages = [{"role": "user", "content": user_text}]
        prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        
        ai_response = generate(
            model, 
            tokenizer, 
            prompt=prompt, 
            max_tokens=512, 
            verbose=False
        )
        
        #return jsonify({
        #    "label": "MLX Intelligent Analysis",
        #    "confidence": ai_response.strip()
        #})
        return ai_response.strip()
        
    except Exception as e:
        return jsonify({"error": f"MLX Inference Error: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(threaded=False)