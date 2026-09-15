import importlib.util
from pathlib import Path
import unittest
import torch

path=Path(__file__).parents[1]/'custom_nodes'/'SecondUnit-PoseFollow'/'__init__.py'
spec=importlib.util.spec_from_file_location('pose_follow_node',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class PoseFollowTests(unittest.TestCase):
    def fixture(self,n):
        h,w=20,30
        points=[[15.,6.,1.] for _ in range(18)]
        points[10]=[15.,18.,1.];points[13]=[15.,18.,1.]
        pose={'canvas_width':w,'canvas_height':h,'people':[{'pose_keypoints_2d':[v for p in points for v in p]}]}
        images=torch.arange(n,dtype=torch.float32).reshape(n,1,1,1).expand(n,h,w,3)/max(n,1)
        return images,[pose for _ in range(n)]

    def test_preserves_frame_order_and_only_pads_last(self):
        images,poses=self.fixture(83)
        out,source,padded,_=module.SecondUnitPoseFollowGuide().prepare(images,poses,target_x=.5,target_feet_y=.9,scale_response=0,min_scale=1,max_scale=1)
        self.assertEqual((source,padded),(83,90))
        torch.testing.assert_close(out[:83],images)
        torch.testing.assert_close(out[83:],images[-1:].expand(7,-1,-1,-1))

    def test_already_valid_h3_length_is_not_extended(self):
        images,poses=self.fixture(22)
        out,source,padded,_=module.SecondUnitPoseFollowGuide().prepare(images,poses)
        self.assertEqual((source,padded,out.shape[0]),(22,22,22))

    def test_missing_person_does_not_invent_motion(self):
        images,poses=self.fixture(5)
        poses[2]={'people':[]}
        with self.assertRaisesRegex(ValueError,'Frame 2'):
            module.SecondUnitPoseFollowGuide().prepare(images,poses)


if __name__=='__main__':unittest.main()
