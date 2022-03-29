import gtsam
import matplotlib.pyplot as plt
import numpy as np
from gtsam import NavState, Point3, Pose3, Rot3
from gtsam.symbol_shorthand import B, V, X
from mpl_toolkits.mplot3d import Axes3D
from scipy.spatial.transform import Rotation as R

from dataloader import *

BIAS_KEY = B(0)


class AUViSAM:
    def __init__(self):
        '''
        The nodes on the graph will be gtsam.NavState, which is essentially a
        SE_2(3) lie group representation of the state of the vehicle.

        For this script, will be testing out the use of the IMU, depth sensor, 
        odometry, and velocity logger.
        '''

        # Initialization of some parameters
        self.dt = 1e-6
        self.priorNoise = gtsam.noiseModel.Isotropic.Sigma(6, 0.1)
        self.velNoise = gtsam.noiseModel.Isotropic.Sigma(3, 0.1)

        # IMU shiz
        acc_bias = np.array([0.067, 0.115, 0.320])
        gyro_bias = np.array([0.067, 0.115, 0.320])
        bias = gtsam.imuBias.ConstantBias(acc_bias, gyro_bias)
        self.params = gtsam.PreintegrationParams.MakeSharedU(9.81)
        self.pim = gtsam.PreintegratedImuMeasurements(
            self.params, bias)

        # Load data
        self.iekf_states = read_iekf_states('states.csv')
        self.iekf_times = read_state_times('state_times.csv')
        self.imu_times, self.imu = read_imu('full_dataset/imu_adis_ros.csv')
        self.depth_times, self.depth = read_depth_sensor(
            'full_dataset/depth_sensor.csv')

    def get_nav_state(self, time):
        '''
        Get the state from the Invariant EKF at time "time" and store
        as a gtsam.NavState to initialize values and/or set nodes in the graph

        Inputs
        =======
        time: int
            Index of the time in the time vector

        Returns
        =======
        nav_state: gtsam.NavState
            The state at time "time"
        '''
        x = self.iekf_states['x'][time]
        y = self.iekf_states['y'][time]
        z = self.iekf_states['z'][time]
        u = self.iekf_states['u'][time]
        v = self.iekf_states['v'][time]
        r = self.iekf_states['r'][time]
        phi = self.iekf_states['phi'][time]
        theta = self.iekf_states['theta'][time]
        psi = self.iekf_states['psi'][time]

        # Think this is the correct way to do it
        # TODO: is this the correct way to do it?
        r1 = R.from_rotvec([phi, 0, 0])
        r2 = R.from_rotvec([0, theta, 0])
        r3 = R.from_rotvec([0, 0, psi])
        rot_mat = r1.as_matrix() @ r2.as_matrix() @ r3.as_matrix()

        p = gtsam.Point3(x, y, z)
        v = gtsam.Point3(u, v, r)

        pose = Pose3(Rot3(rot_mat), p)
        state = NavState(pose, v)
        return state

    def iSAM(self):
        '''
        Optimize over the graph after each new observation is taken

        TODO: Test with only a few states at first
        '''
        isam = gtsam.ISAM2()

        state_idx = 0
        camera_idx = 0
        imu_idx = 0

        time_elapsed = 0
        imu_time_elapsed = 0

        while state_idx < 100:
            state = self.get_nav_state(state_idx)
            graph = gtsam.NonlinearFactorGraph()
            initial = gtsam.Values()

            if state_idx == 0:
                # Add prior to the graph
                priorPoseFactor = gtsam.PriorFactorPose3(
                    X(state_idx), state.pose(), self.priorNoise)
                graph.add(priorPoseFactor)

                priorVelFactor = gtsam.PriorFactorPoint3(
                    V(state_idx), state.velocity(), self.velNoise)
                graph.add(priorVelFactor)

                # Add values
                initial.insert(X(state_idx), state.pose())
                initial.insert(V(state_idx), state.velocity())


                # IMU information
                acc_bias = np.array([0.067, 0.115, 0.320])
                gyro_bias = np.array([0.067, 0.115, 0.320])
                bias = gtsam.imuBias.ConstantBias(acc_bias, gyro_bias)
                initial.insert(BIAS_KEY, bias)
            else:
                # Compute time difference between states
                dt = self.iekf_times[state_idx] - self.iekf_times[state_idx - 1]
                dt *= 1e-9
                if dt <= 0:
                    state_idx += 1
                    continue
                
                prev_state = self.get_nav_state(state_idx - 1)
                initial.insert(X(state_idx), prev_state.pose())
                initial.insert(V(state_idx), prev_state.velocity())
                print(f'State time: {self.iekf_times[state_idx]*1e-18}')

                while self.iekf_times[state_idx] > self.imu_times[imu_idx]:
                    omega_x = self.imu['omega_x'][imu_idx]
                    omega_y = self.imu['omega_y'][imu_idx]
                    omega_z = self.imu['omega_z'][imu_idx]
                    lin_acc_x = self.imu['ax'][imu_idx]
                    lin_acc_y = self.imu['ay'][imu_idx]
                    lin_acc_z = self.imu['az'][imu_idx]

                    measuredOmega = np.array(
                        [omega_x, omega_y, omega_z]).reshape(-1, 1)
                    measuredAcc = np.array(
                        [lin_acc_x, lin_acc_y, lin_acc_z]).reshape(-1, 1)

                    print(f'\tIMU time: {self.imu_times[imu_idx]*1e-18}')
                    print(f'\tMeasured omega: {measuredOmega.T}')
                    print(f'\tMeasured acc: {measuredAcc.T}')
                    print()
                    imu_idx += 1
            

            state_idx += 1            


def main():
    AUV_SLAM = AUViSAM()
    AUV_SLAM.iSAM()


if __name__ == '__main__':
    main()