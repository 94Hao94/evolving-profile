"""An OS account name is a container, never evidence of project identity."""
import pytest
from lib.relevance import admission_decision,path_artifact_scope_alignment


@pytest.mark.parametrize('home',['/Users/long-owner','/Users/another-owner','/home/linux-owner','~'])
def test_shared_account_path_does_not_rescue_an_unrelated_memory(home):
    prompt=f'处理 {home}/Projects/示例影片项目 内的25段视频，按顺序拼接并添加字幕、背景音乐，输出MP4。'
    relevant={'type':'experience','text':f'文件 {home}/Projects/示例影片项目/15.mp4 已生成，可作为该项目的视频素材。'}
    unrelated={'type':'experience','text':f'配置文件 {home}/.codex/config.toml 记录工具设置。'}
    assert admission_decision(prompt,relevant,deep=True)['decision']=='qualified'
    assert not path_artifact_scope_alignment(prompt,unrelated['text'])['qualified']
    assert admission_decision(prompt,unrelated,deep=True)['decision']=='rejected_path_scope_mismatch'
