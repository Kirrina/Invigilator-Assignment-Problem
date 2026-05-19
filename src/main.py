import pulp
import os
from data_preprocessing import preprocess_data, manual_data_adjustment
from model_builder import build_model
from solver import solve_model

def main():
    """
    Main orchestrator function.
    
    Steps:
    1. Load and validate input Excel file
    2. Preprocess data and extract parameters
    3. Interactive data adjustment menu
    4. Build ILP model
    5. Solve and export results
    
    Returns:
        bool: True if successful, False if failed
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    file_excel = os.path.join(project_root, 'input', 'Dataset_Anonymized_Invigilator_Assignment_Problem.xlsx')
    
    # Validate file exists
    if not os.path.exists(file_excel):
        print("=" * 60)
        print("❌ ERROR: Input file not found!")
        print("=" * 60)
        print(f"\nExpected location: {file_excel}")
        print(f"\nPlease ensure:")
        print("  1. Create an 'input' folder in the project root")
        print("  2. Place the Excel file in that folder")
        print("  3. File must be named: 'Dataset_Anonymized_Invigilator_Assignment_Problem.xlsx'")
        print("\nCurrent working directory:", os.getcwd())
        print("Project root:", project_root)
        return False
    
    try:
        # 1. Read and preprocess data
        print("\n[Step 1] Loading and validating Excel file...")
        data_model = preprocess_data(file_excel)
        
        # 2. Interactive data adjustment
        print("\n[Step 2] Data adjustment menu...")
        manual_data_adjustment(data_model)
        
        # 3. Build ILP model
        print("\n[Step 3] Building ILP model...")
        prob, X = build_model(data_model)
        
        # 4. Solve
        print("\n[Step 4] Solving optimization problem...")
        solve_model(prob, X, data_model)
        
        return True
    
    except FileNotFoundError as e:
        print(f"\n❌ FILE ERROR: {e}")
        return False
    except ValueError as e:
        print(f"\n❌ DATA VALIDATION ERROR: {e}")
        return False
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("\n" + "="*60)
    print("   IAP - INVIGILATOR ASSIGNMENT PROBLEM SOLVER")
    print("="*60)
    
    success = main()
    
    if success:
        print("\n" + "="*60)
        print("✓ Program completed successfully!")
        print("="*60 + "\n")
    else:
        print("\n" + "="*60)
        print("✗ Program failed - please check the errors above")
        print("="*60 + "\n")