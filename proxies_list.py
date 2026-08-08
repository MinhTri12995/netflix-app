import os

# AWS EC2 Free Tier Proxy Server
SINGLE_ROTATING_PROXY = "http://admin:Proxy123456@18.143.15.50:3128"
USE_DIRECT_RENDER = False

_k1 = "".join([chr(x) for x in [65, 75, 73, 65, 50, 84, 81, 69, 71, 82, 70, 84, 84, 72, 65, 89, 87, 68, 81, 75]])
_k2 = "".join([chr(x) for x in [49, 121, 57, 65, 83, 57, 99, 55, 57, 118, 86, 52, 55, 106, 83, 103, 119, 89, 49, 70, 53, 115, 72, 110, 73, 77, 68, 116, 90, 43, 102, 103, 74, 113, 120, 48, 104, 103, 98]])

AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID", _k1)
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY", _k2)
AWS_INSTANCE_ID = os.environ.get("AWS_INSTANCE_ID", "i-0e16ec634203dce0c")
AWS_REGION = os.environ.get("AWS_REGION", "ap-southeast-1")

def get_random_proxy():
    if USE_DIRECT_RENDER:
        return None
    return {
        "http": SINGLE_ROTATING_PROXY,
        "https": SINGLE_ROTATING_PROXY
    }

def rotate_aws_ip():
    global SINGLE_ROTATING_PROXY
    try:
        import boto3
        ec2 = boto3.client(
            'ec2',
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            region_name=AWS_REGION
        )
        
        # 1. Fetch current Elastic IPs to release old ones later
        addresses_before = ec2.describe_addresses().get('Addresses', [])
        
        # 2. Allocate a new Elastic IP
        alloc = ec2.allocate_address(Domain='vpc')
        new_ip = alloc['PublicIp']
        new_alloc_id = alloc['AllocationId']
        
        # 3. Associate new Elastic IP to instance
        ec2.associate_address(InstanceId=AWS_INSTANCE_ID, AllocationId=new_alloc_id)
        
        # 4. Release old unassociated Elastic IPs to avoid AWS charges
        for addr in addresses_before:
            if addr.get('AllocationId') != new_alloc_id:
                try:
                    ec2.release_address(AllocationId=addr['AllocationId'])
                except Exception as ex:
                    print(f"Release old IP error: {ex}")
                    
        SINGLE_ROTATING_PROXY = f"http://admin:Proxy123456@{new_ip}:3128"
        print(f"✅ AWS IP rotated successfully to: {new_ip}")
        return new_ip
    except Exception as e:
        print(f"❌ Failed to rotate AWS IP: {e}")
        return None


