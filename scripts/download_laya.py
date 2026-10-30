"""Explicit first-time download of the pinned optional CPU model."""
import argparse
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination',type=Path,required=True)
    args=parser.parse_args()
    from huggingface_hub import snapshot_download
    snapshot_download('convaiinnovations/laya',revision='1c5edc17a7acd8701df6fc341c0d179f1c62c982',
                      local_dir=str(args.destination.resolve()),
                      allow_patterns=['model.safetensors','rl_agent_config.json','encoder/config.json',
                                      'tokenizer/tokenizer.json','tokenizer/tokenizer_config.json','LICENSE*','README.md'])
    print('Pinned model downloaded. Supply this directory to setup_stack.py --model-path.')


if __name__=='__main__': main()
